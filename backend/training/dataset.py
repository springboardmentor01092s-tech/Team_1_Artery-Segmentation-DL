"""Manifest-only pairing and a bounded, streaming, single-case NIfTI cache."""
from __future__ import annotations

from dataclasses import dataclass
import csv
import gzip
import hashlib
from io import BytesIO
import json
import math
import os
from pathlib import Path, PurePosixPath
import tempfile

import nibabel as nib
import numpy as np


CHUNK_BYTES = 1024 * 1024
VOXEL_WARNING = (
    "Voxel-grid-only research segmentation: reference spatial units may be unknown. "
    "Matching numerical grids do not prove anatomical registration. Physical measurements are not authorized."
)


class DataError(ValueError):
    pass


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def file_version(path):
    s = path.stat()
    return (s.st_size, s.st_mtime_ns, s.st_ctime_ns, s.st_dev, s.st_ino)


@dataclass(frozen=True)
class Case:
    case_id: int
    split: str
    ct: Path
    mask: Path
    ct_version: tuple
    mask_version: tuple


@dataclass
class Index:
    root: Path
    manifest: Path
    cases: dict[int, Case]
    assignments: dict[int, str]
    manifest_fingerprint: str
    split_fingerprint: str
    source_fingerprint: str
    testing_excluded: int
    raw_manifest_sha256: str
    dataset_identity: dict

    def ids(self, split):
        if split not in ("Training", "Val"):
            raise DataError("Only Training and Val may be indexed.")
        return sorted(i for i, case in self.cases.items() if case.split == split)

    def case(self, case_id, split):
        if split not in ("Training", "Val") or case_id not in self.cases:
            raise DataError("Case is not in the permitted cohort.")
        case = self.cases[case_id]
        if case.split != split:
            raise DataError("Case does not belong to the requested split.")
        return case

    def contract(self):
        return {"manifest_fingerprint": self.manifest_fingerprint,
                "split_fingerprint": self.split_fingerprint,
                "dataset_identity": self.dataset_identity,
                "storage": {"root": str(self.root), "manifest": str(self.manifest),
                            "raw_manifest_sha256": self.raw_manifest_sha256,
                            "source_version_fingerprint": self.source_fingerprint},
                "training_case_ids": self.ids("Training"), "validation_case_ids": self.ids("Val")}


def _member(value, group, case_id, kind):
    text = value.replace("\\", "/")
    parts = PurePosixPath(text).parts
    if text.startswith("/") or ":" in text or ".." in parts or parts != (group, f"{case_id}.{kind}.nii.gz"):
        raise DataError("Manifest member is not an exact, safe case/role mapping.")
    return parts


def build_index(root, manifest, *, expected_training=700, expected_validation=50, dataset_identity=None):
    root, manifest = Path(root).resolve(), Path(manifest).resolve()
    if not root.is_dir():
        raise DataError("Dataset root is unavailable.")
    payload = manifest.read_bytes()
    import io
    reader = csv.DictReader(io.StringIO(payload.decode("utf-8-sig")))
    required = {"case_id", "split", "archive_group", "ct_member", "mask_member"}
    if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)) or not required.issubset(reader.fieldnames):
        raise DataError("Extraction-manifest columns are missing or duplicated.")
    assignments, cases, paths, versions, records = {}, {}, set(), [], []
    for row in reader:
        if None in row or any(value is None for value in row.values()):
            raise DataError("Malformed manifest row.")
        text = row["case_id"].strip()
        if not text.isascii() or not text.isdecimal() or not 1 <= int(text) <= 1000:
            raise DataError("Invalid ImageCAS case ID.")
        cid, split = int(text), row["split"].strip()
        if cid in assignments or split not in ("Training", "Val", "Testing"):
            raise DataError("Duplicate case ID or invalid split.")
        assignments[cid] = split
        # Testing records are excluded before inspecting member names or any paths.
        if split == "Testing":
            records.append({"case_id": cid, "split": split})
            continue
        start = ((cid - 1) // 200) * 200 + 1
        group = f"{start}-{start + 199}"
        if row["archive_group"] != group or (row.get("archive_file") and row["archive_file"] != group + ".zip"):
            raise DataError("Archive-group mapping is inconsistent.")
        pair = []
        for column, kind in (("ct_member", "img"), ("mask_member", "label")):
            parts = _member(row[column], group, cid, kind)
            path = root.joinpath(split, *parts).resolve()
            if not path.is_relative_to(root / split) or not path.is_file():
                raise DataError(f"Missing or unsafe partner for case {cid}.")
            identity = os.path.normcase(str(path))
            if identity in paths:
                raise DataError("A source path is reused across cases or roles.")
            paths.add(identity)
            pair.append(path)
        ct_version, mask_version = file_version(pair[0]), file_version(pair[1])
        cases[cid] = Case(cid, split, *pair, ct_version, mask_version)
        records.append({"case_id": cid, "split": split,
                        "ct_member": "/".join(_member(row["ct_member"], group, cid, "img")),
                        "mask_member": "/".join(_member(row["mask_member"], group, cid, "label"))})
        versions.append([cid, split, str(pair[0]), ct_version, str(pair[1]), mask_version])
    index = Index(root, manifest, cases, assignments, fingerprint(sorted(records, key=lambda r: r["case_id"])),
                  fingerprint(sorted(assignments.items())), fingerprint(sorted(versions)),
                  sum(s == "Testing" for s in assignments.values()), hashlib.sha256(payload).hexdigest(), {})
    if len(index.ids("Training")) != expected_training or len(index.ids("Val")) != expected_validation:
        raise DataError("Indexed cohort counts differ from explicit expectations.")
    from .identity import build_identity
    index.dataset_identity = build_identity(index, records, dataset_identity)
    return index


@dataclass(frozen=True)
class Header:
    shape: tuple
    dtype: np.dtype
    spacing: tuple
    affine: np.ndarray
    sform: np.ndarray
    units: str
    offset: int
    slope: float
    intercept: float


def read_header(path):
    opener = gzip.open if path.name.lower().endswith(".gz") else open
    with opener(path, "rb") as stream:
        raw = stream.read(348)
        if raw[4:12] == b"n+2\x00\r\n\x1a\n":
            raw += stream.read(192)
    if len(raw) >= 348 and raw[344:348] == b"n+1\x00":
        h = nib.Nifti1Header.from_fileobj(BytesIO(raw), check=False)
        minimum = 352
    elif len(raw) == 540 and raw[4:12] == b"n+2\x00\r\n\x1a\n":
        h = nib.Nifti2Header.from_fileobj(BytesIO(raw), check=False)
        minimum = 544
    else:
        raise DataError("Not a single-file NIfTI-1/2 header.")
    shape, spacing = h.get_data_shape(), h.get_zooms()
    if len(shape) != 3 or any(d < 1 or d > 1024 for d in shape) or math.prod(shape) > 134_217_728:
        raise DataError("Unsupported or oversized 3D shape.")
    if not np.isfinite(spacing).all() or any(d <= 0 for d in spacing):
        raise DataError("Invalid voxel spacing.")
    scode, qcode = int(h["sform_code"]), int(h["qform_code"])
    if scode not in range(1, 6) or qcode not in range(6):
        raise DataError("A valid coded sform is required.")
    sform, affine = h.get_sform(), h.get_best_affine()
    if (not np.isfinite(affine).all() or abs(np.linalg.det(affine[:3, :3])) < 1e-12
            or not np.allclose(np.linalg.norm(affine[:3, :3], axis=0), spacing, rtol=0, atol=1e-6)
            or nib.aff2axcodes(affine) != ("L", "A", "S")):
        raise DataError("Invalid affine, spacing or expected LAS orientation.")
    if qcode and not np.allclose(h.get_qform(), sform, rtol=0, atol=1e-5):
        raise DataError("Conflicting coded qform and sform.")
    # An uncoded qform is intentionally not used to establish registration.
    slope, intercept = h.get_slope_inter()
    slope, intercept = (1., 0.) if slope is None else (float(slope), float(intercept))
    offset = float(h["vox_offset"])
    if not all(math.isfinite(v) for v in (slope, intercept, offset)) or offset != int(offset) or not minimum <= offset <= 16 * 1024 * 1024:
        raise DataError("Invalid scaling or data offset.")
    return Header(tuple(shape), h.get_data_dtype(), tuple(float(v) for v in spacing), affine,
                  sform, h.get_xyzt_units()[0], int(offset), slope, intercept)


def check_pair(index, case, patch_size=(64, 64, 64)):
    if index.case(case.case_id, case.split) != case:
        raise DataError("Unindexed case.")
    if file_version(case.ct) != case.ct_version or file_version(case.mask) != case.mask_version:
        raise DataError("Source changed after indexing.")
    ct, mask = read_header(case.ct), read_header(case.mask)
    if ct.dtype.kind != "i" or ct.dtype.itemsize != 2 or mask.dtype.kind != "f" or mask.dtype.itemsize != 8:
        raise DataError("Expected int16 CT and float64 reference storage.")
    if (ct.shape != mask.shape or not np.allclose(ct.spacing, mask.spacing, rtol=0, atol=1e-6)
            or not np.allclose(ct.affine, mask.affine, rtol=0, atol=1e-5)
            or not np.allclose(ct.sform, mask.sform, rtol=0, atol=1e-5)):
        raise DataError("CT/reference numerical grids disagree.")
    if ct.units != "mm" or mask.units not in ("unknown", "mm"):
        raise DataError("Unexpected source-unit declaration.")
    if len(patch_size) != 3 or any(size < 4 or size % 4 or size > dim for size, dim in zip(patch_size, ct.shape)):
        raise DataError("Volume cannot supply the specified unpadded compatible patch.")
    if file_version(case.ct) != case.ct_version or file_version(case.mask) != case.mask_version:
        raise DataError("Source changed during header inspection.")
    return ct, mask


def _chunks(path, header):
    opener = gzip.open if path.name.lower().endswith(".gz") else open
    remaining = math.prod(header.shape) * header.dtype.itemsize
    size = CHUNK_BYTES // header.dtype.itemsize * header.dtype.itemsize
    with opener(path, "rb") as stream:
        stream.seek(header.offset)
        while remaining:
            data = stream.read(min(size, remaining))
            if len(data) != min(size, remaining):
                raise DataError("Truncated voxel payload.")
            yield np.frombuffer(data, dtype=header.dtype)
            remaining -= len(data)


def normalize_patch(raw, slope=1., intercept=0.):
    values = np.array(raw, dtype=np.float32, copy=True, order="C")
    values *= slope
    values += intercept
    if not np.isfinite(values).all():
        raise DataError("Non-finite CT patch.")
    np.clip(values, -200., 800., out=values)
    values += 200.
    values /= 1000.
    return values


class SingleCaseCache:
    """One raw int16 CT + one uint8 mask; never retain a whole float64 mask."""
    def __init__(self, index, patch_size=(64, 64, 64), max_bytes=512 * 1024 * 1024, cache_directory=None):
        self.index, self.patch_size, self.max_bytes = index, tuple(patch_size), max_bytes
        self.cache_directory = Path(cache_directory).resolve() if cache_directory else None
        if self.cache_directory and any(self.cache_directory.is_relative_to(p) for p in
                                        (index.root, index.manifest.parent, Path(__file__).resolve().parents[2])):
            raise DataError("Disk cache must be outside repository and input directories.")
        self._temporary = None
        self._mapped = []
        self.clear()

    def clear(self):
        self.case = self.ct = self.mask = self.ct_header = self.foreground_counts = None
        for array in self._mapped:
            array._mmap.close()
        self._mapped = []
        if self._temporary:
            self._temporary.cleanup()  # Only this instance's uniquely owned case files.
            self._temporary = None

    def _allocate(self, shape, dtype, name):
        if not self.cache_directory:
            return np.empty(shape, dtype=dtype, order="F")
        if self._temporary is None:
            self.cache_directory.mkdir(parents=True, exist_ok=True)
            self._temporary = tempfile.TemporaryDirectory(prefix="vascuai-single-case-", dir=self.cache_directory)
        array = np.memmap(Path(self._temporary.name) / name, dtype=dtype, mode="w+", shape=shape, order="F")
        self._mapped.append(array)
        return array

    def load(self, case):
        try:
            self._load_case(case)
        except BaseException:
            self.clear()
            raise

    def _load_case(self, case):
        if self.case == case:
            if file_version(case.ct) != case.ct_version or file_version(case.mask) != case.mask_version:
                raise DataError("Cached source changed.")
            return
        self.clear()  # Evict before allocating the next pair.
        ct_header, mask_header = check_pair(self.index, case, self.patch_size)
        if math.prod(ct_header.shape) * 3 > self.max_bytes:
            raise DataError("Case exceeds the explicit cache byte budget.")
        ct = self._allocate(ct_header.shape, ct_header.dtype, "ct.dat")
        flat, offset = ct.reshape(-1, order="F"), 0
        for values in _chunks(case.ct, ct_header):
            flat[offset:offset + values.size] = values
            offset += values.size
        mask = self._allocate(mask_header.shape, np.uint8, "mask.dat")
        flat, offset = mask.reshape(-1, order="F"), 0
        for raw in _chunks(case.mask, mask_header):
            values = raw if (mask_header.slope, mask_header.intercept) == (1., 0.) else raw * mask_header.slope + mask_header.intercept
            if not np.isfinite(values).all() or np.any((values != 0) & (values != 1)):
                raise DataError("Reference must contain finite binary 0/1 values before conversion.")
            flat[offset:offset + values.size] = values.astype(np.uint8)
            offset += values.size
        counts = np.fromiter((np.count_nonzero(mask[i]) for i in range(mask.shape[0])), dtype=np.int64)
        if not counts.sum():
            raise DataError("Empty foreground reference is outside this training contract.")
        if file_version(case.ct) != case.ct_version or file_version(case.mask) != case.mask_version:
            raise DataError("Source changed while loading.")
        self.case, self.ct, self.mask = case, ct, mask
        self.ct_header, self.foreground_counts = ct_header, counts

    def patch(self, origin):
        if self.case is None or len(origin) != 3 or any(s < 0 or s + n > d for s, n, d in zip(origin, self.patch_size, self.ct.shape)):
            raise DataError("Patch lies outside the active case.")
        region = tuple(slice(start, start + n) for start, n in zip(origin, self.patch_size))
        x = normalize_patch(self.ct[region], self.ct_header.slope, self.ct_header.intercept)
        y = np.array(self.mask[region], dtype=np.float32, copy=True, order="C")
        return x[None, None], y[None, None]
