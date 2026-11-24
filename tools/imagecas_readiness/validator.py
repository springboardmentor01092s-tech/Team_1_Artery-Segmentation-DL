"""Validate explicit ImageCAS manifests without altering source data.

Only an explicitly requested report is written. No discovery, model imports,
resampling, normalization or automatic approval is performed.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from dataclasses import dataclass
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import posixpath
import re
import sys
import xml.etree.ElementTree as ET
import zipfile


LABELS = ("Training", "Val", "Testing")
ELIGIBLE = frozenset(("Training", "Val"))
STATUS_PRIORITY = (
    "BLOCKED_MANIFEST", "BLOCKED_INTEGRITY", "BLOCKED_MISSING_DATA",
    "BLOCKED_GEOMETRY", "NOT_VERIFIED",
)
XML_NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
MAX_XML_BYTES = 8 * 1024 * 1024
CHUNK_BYTES = 1024 * 1024
AFFINE_ATOL = 1e-5
SPACING_ATOL = 1e-6


class ManifestError(ValueError):
    """Safe manifest parsing error, without source values or filesystem paths."""


@dataclass(frozen=True)
class Config:
    split_manifest: Path
    split_column: str
    pair_manifest: Path | None = None
    sheet: str | None = None
    header_row: int = 2
    id_column: str = "FileName"
    compare_split: Path | None = None
    source_roots: tuple[Path, ...] = ()
    expected_counts: dict[str, int] | None = None
    verify_hashes: bool = False
    deep_label_scan: bool = False


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _xml(archive, name):
    try:
        info = archive.getinfo(name)
        if info.file_size > MAX_XML_BYTES:
            raise ManifestError("Workbook XML exceeds the supported 8 MiB member limit.")
        value = archive.read(info)
        if b"<!DOCTYPE" in value.upper() or b"<!ENTITY" in value.upper():
            raise ManifestError("Workbook XML declarations are unsupported.")
        return ET.fromstring(value)
    except (KeyError, ET.ParseError) as exc:
        raise ManifestError("Workbook XML is missing or malformed.") from exc


def _xlsx_rows(path, sheet, header_row):
    """Read stored cells only, using stdlib ZIP/XML; never evaluate formulas."""
    if not sheet or header_row < 1:
        raise ManifestError("XLSX requires an explicit sheet and positive header row.")
    with zipfile.ZipFile(path) as archive:
        if len(archive.namelist()) != len(set(archive.namelist())):
            raise ManifestError("Workbook contains duplicate archive members.")
        workbook = _xml(archive, "xl/workbook.xml")
        sheets = workbook.findall("s:sheets/s:sheet", XML_NS)
        selected = [item for item in sheets if item.get("name") == sheet]
        if len(selected) != 1:
            raise ManifestError("Selected workbook sheet was not found uniquely.")
        relations = _xml(archive, "xl/_rels/workbook.xml.rels")
        rid = selected[0].get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        relation = [item for item in relations if item.get("Id") == rid]
        if len(relation) != 1 or relation[0].get("TargetMode") == "External":
            raise ManifestError("Selected worksheet relationship is invalid.")
        target = relation[0].get("Target", "")
        member = posixpath.normpath(target.lstrip("/") if target.startswith("/") else "xl/" + target)
        if not member.startswith("xl/") or "\\" in member:
            raise ManifestError("Worksheet relationship leaves the workbook.")
        strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            strings = ["".join(item.itertext()) for item in _xml(archive, "xl/sharedStrings.xml")]
        document = _xml(archive, member)
        rows = []
        seen_rows = set()
        for row in document.findall("s:sheetData/s:row", XML_NS):
            number = int(row.attrib["r"])
            if number in seen_rows:
                raise ManifestError("Worksheet contains duplicate row numbers.")
            seen_rows.add(number)
            cells = {}
            for cell in row:
                address = cell.get("r", "")
                match = re.fullmatch(r"([A-Z]+)([0-9]+)", address)
                if not match or int(match[2]) != number or match[1] in cells:
                    raise ManifestError("Worksheet cell address is invalid or duplicated.")
                if cell.find("s:f", XML_NS) is not None:
                    raise ManifestError("Formula cells are unsupported in split manifests.")
                value = cell.find("s:v", XML_NS)
                text = "" if value is None else value.text or ""
                if cell.get("t") == "s":
                    index = int(text)
                    if not 0 <= index < len(strings):
                        raise ManifestError("Invalid workbook shared-string index.")
                    text = strings[index]
                elif cell.get("t") == "inlineStr":
                    inline = cell.find("s:is", XML_NS)
                    text = "" if inline is None else "".join(inline.itertext())
                cells[match[1]] = text
            rows.append((number, cells))
        headers = [cells for number, cells in rows if number == header_row]
        if len(headers) != 1:
            raise ManifestError("Selected workbook header row is missing.")
        header = {column: value.strip() for column, value in headers[0].items() if value.strip()}
        _check_columns(list(header.values()))
        return [(number, {name: cells.get(column, "") for column, name in header.items()})
                for number, cells in rows if number > header_row and any(v.strip() for v in cells.values())]


def _check_columns(columns):
    if not columns or any(not c for c in columns) or len(set(columns)) != len(columns):
        raise ManifestError("Manifest has blank or duplicate column names.")


def read_rows(path, *, sheet=None, header_row=2):
    try:
        if path.suffix.lower() == ".xlsx":
            return _xlsx_rows(path, sheet, header_row)
        if path.suffix.lower() != ".csv":
            raise ManifestError("Only explicit CSV and XLSX sources are supported.")
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            _check_columns(reader.fieldnames)
            rows = []
            for number, row in enumerate(reader, 2):
                if None in row or any(value is None for value in row.values()):
                    raise ManifestError("CSV row has an inconsistent column count.")
                if any(v.strip() for v in row.values()):
                    rows.append((number, row))
            return rows
    except ManifestError:
        raise
    except (OSError, ValueError, KeyError, IndexError, csv.Error, zipfile.BadZipFile, RuntimeError) as exc:
        raise ManifestError("Manifest could not be read safely.") from exc


def case_id(value):
    text = str(value).strip()
    if not re.fullmatch(r"[0-9]+(?:\.0+)?", text):
        raise ValueError("Invalid identifier")
    result = int(text.split(".")[0])
    if result < 1:
        raise ValueError("Invalid identifier")
    return result


class Findings:
    def __init__(self):
        self.issues = []

    def add(self, code, message, *, status=None, severity="error", **context):
        self.issues.append({"code": code, "severity": severity, "message": message,
                            "blocking_status": status, **context})

    def decision(self):
        statuses = {item["blocking_status"] for item in self.issues}
        return next((status for status in STATUS_PRIORITY if status in statuses), "READY_FOR_REVIEW")


def _assignments(rows, config, findings, source):
    assignments = defaultdict(set)
    occurrences = Counter()
    counts = Counter()
    for number, row in rows:
        if config.id_column not in row or config.split_column not in row:
            raise ManifestError("Required identifier or selected split column is missing.")
        try:
            identifier = case_id(row[config.id_column])
        except ValueError:
            findings.add("INVALID_CASE_ID", "Missing or invalid case identifier.", status="BLOCKED_MANIFEST", row=number, source=source)
            continue
        label = row[config.split_column].strip()
        occurrences[identifier] += 1
        if label not in LABELS:
            findings.add("INVALID_SPLIT", "Unexpected or missing split label.", status="BLOCKED_MANIFEST", case_id=identifier, row=number, source=source)
        else:
            assignments[identifier].add(label)
            counts[label] += 1
    for identifier, count in occurrences.items():
        if count > 1:
            findings.add("DUPLICATE_CASE_ID", "Case identifier occurs more than once.", status="BLOCKED_MANIFEST", case_id=identifier, source=source)
        if len(assignments[identifier]) > 1:
            findings.add("SPLIT_LEAKAGE", "One identifier is assigned across splits.", status="BLOCKED_MANIFEST", case_id=identifier, source=source)
    valid = {identifier: next(iter(labels)) for identifier, labels in assignments.items()
             if len(labels) == 1 and occurrences[identifier] == 1}
    if not rows:
        findings.add("EMPTY_SPLIT", "Selected split contains no records.", status="BLOCKED_MANIFEST")
    return valid, {label: counts[label] for label in LABELS}


def _inside(path, roots):
    return any(path.is_relative_to(root) for root in roots)


def _path(value, base, roots, findings, identifier, role):
    if not value.strip():
        return None
    try:
        path = Path(value.strip())
        path = (path if path.is_absolute() else base / path).resolve()
        if not _inside(path, roots):
            findings.add("PATH_OUTSIDE_ROOTS", "Source path is outside approved roots; it was not opened.", status="BLOCKED_MANIFEST", case_id=identifier, role=role)
            return None
        return path
    except (OSError, ValueError, RuntimeError):
        findings.add("INVALID_PATH", "Source path could not be resolved.", status="BLOCKED_MANIFEST", case_id=identifier, role=role)
        return None


def _filename_id(path):
    match = re.fullmatch(r"(?:([0-9]+)\.(?:img|label)|case_([0-9]+)_(?:ct|reference_mask))\.nii(?:\.gz)?", path.name, re.IGNORECASE)
    return int(match[1] or match[2]) if match else None


def _filename_role(path):
    if re.fullmatch(r"[0-9]+\.img\.nii(?:\.gz)?|case_[0-9]+_ct\.nii(?:\.gz)?", path.name, re.IGNORECASE):
        return "ct"
    if re.fullmatch(r"[0-9]+\.label\.nii(?:\.gz)?|case_[0-9]+_reference_mask\.nii(?:\.gz)?", path.name, re.IGNORECASE):
        return "reference"
    return None


def _version(path):
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_dev, stat.st_ino


def inspect_header(path):
    """Read <=540 header bytes, not extensions or the image data proxy."""
    import nibabel as nib
    import numpy as np
    opener = gzip.open if path.name.lower().endswith(".nii.gz") else open
    with opener(path, "rb") as stream:
        raw = stream.read(348)
        if raw[4:12] == b"n+2\x00\r\n\x1a\n":
            raw += stream.read(192)
    from io import BytesIO
    if len(raw) >= 348 and raw[344:348] == b"n+1\x00":
        header = nib.Nifti1Header.from_fileobj(BytesIO(raw), check=False)
        minimum_offset = 352
    elif len(raw) >= 540 and raw[4:12] == b"n+2\x00\r\n\x1a\n":
        header = nib.Nifti2Header.from_fileobj(BytesIO(raw), check=False)
        minimum_offset = 544
    else:
        raise ValueError("Invalid single-file NIfTI header")
    shape = header.get_data_shape()
    spacing = header.get_zooms()
    affine = header.get_best_affine()
    qcode, scode = int(header["qform_code"]), int(header["sform_code"])
    slope, intercept = header.get_slope_inter()
    slope, intercept = (1.0, 0.0) if slope is None else (float(slope), float(intercept))
    offset = float(header["vox_offset"])
    dtype = header.get_data_dtype()
    issues = []
    if len(shape) != 3 or any(dim < 1 for dim in shape):
        issues.append("UNSUPPORTED_DIMENSIONS")
    if len(spacing) != 3 or not np.isfinite(spacing).all() or any(x <= 0 for x in spacing):
        issues.append("INVALID_SPACING")
    if not np.isfinite(affine).all() or abs(np.linalg.det(affine[:3, :3])) < 1e-12:
        issues.append("INVALID_AFFINE")
        orientation = [None, None, None]
    else:
        orientation = list(nib.aff2axcodes(affine))
        if None in orientation:
            issues.append("INVALID_ORIENTATION")
        if len(spacing) == 3 and np.isfinite(spacing).all() and not np.allclose(
            np.linalg.norm(affine[:3, :3], axis=0), spacing, rtol=0, atol=SPACING_ATOL
        ):
            issues.append("AFFINE_SPACING_INCONSISTENT")
    if qcode not in range(6) or scode not in range(6) or (qcode == 0 and scode == 0):
        issues.append("UNCODED_OR_INVALID_TRANSFORM")
    if qcode and scode and not np.allclose(header.get_qform(), header.get_sform(), rtol=0, atol=AFFINE_ATOL):
        issues.append("CONFLICTING_CODED_TRANSFORMS")
    if dtype.kind not in "uif" or dtype.itemsize > 8 or not math.isfinite(slope) or not math.isfinite(intercept):
        issues.append("UNSUPPORTED_DTYPE_OR_SCALING")
    if not math.isfinite(offset) or offset < minimum_offset or offset != int(offset) or offset > 16 * 1024 * 1024:
        issues.append("INVALID_DATA_OFFSET")
    return {"shape": list(shape), "spacing": [float(x) for x in spacing],
            "units": list(header.get_xyzt_units()), "affine": affine.tolist(),
            "qform_code": qcode, "sform_code": scode, "orientation": orientation,
            "dtype": str(dtype), "scaling": {"slope": slope, "intercept": intercept},
            "header_issues": issues}, (dtype, shape, offset, slope, intercept)


def scan_labels(path, layout):
    """Stream on-disk scalar voxels in <=1 MiB chunks, including NIfTI scaling."""
    import numpy as np
    dtype, shape, offset, slope, intercept = layout
    count = math.prod(shape)
    remaining = count * dtype.itemsize
    chunk_size = max(dtype.itemsize, CHUNK_BYTES // dtype.itemsize * dtype.itemsize)
    unexpected = nonfinite = foreground = seen = 0
    opener = gzip.open if path.name.lower().endswith(".nii.gz") else open
    with opener(path, "rb") as stream:
        stream.seek(int(offset))
        while remaining:
            requested = min(remaining, chunk_size)
            data = stream.read(requested)
            if len(data) != requested:
                raise ValueError("Truncated label payload")
            values = np.frombuffer(data, dtype=dtype).astype(np.float64)
            with np.errstate(over="ignore", invalid="ignore"):
                values *= slope
                values += intercept
            finite = np.isfinite(values)
            nonfinite += int(np.count_nonzero(~finite))
            unexpected += int(np.count_nonzero(finite & (values != 0) & (values != 1)))
            foreground += int(np.count_nonzero(finite & (values > 0)))
            seen += values.size
            remaining -= requested
    return {"status": "PASS" if not (unexpected or nonfinite) else "FAIL",
            "voxels_scanned": seen, "foreground_voxels": foreground,
            "unexpected_label_voxels": unexpected, "nonfinite_voxels": nonfinite,
            "contract": "finite binary {0,1}; foreground = scaled label > 0",
            "chunk_bytes": CHUNK_BYTES}


def _pairs(config, assignments, findings):
    summary = {"records": 0, "eligible_records": 0, "skipped_test_records": 0,
               "existing_ct": 0, "missing_ct": 0, "existing_reference": 0,
               "missing_reference": 0, "complete_pairs": 0, "unmatched_pairs": 0,
               "missing_pair_records": 0, "declared_source_status_counts": {}}
    if config.pair_manifest is None:
        findings.add("NO_PAIR_MANIFEST", "No pairing source supplied; source readiness was not checked.", status="NOT_VERIFIED", severity="unverified")
        return summary, []
    roots = tuple(root.resolve() for root in config.source_roots)
    if not roots or any(not root.is_dir() for root in roots):
        raise ManifestError("Pair validation requires existing, explicitly approved source roots.")
    rows = read_rows(config.pair_manifest)
    split_binding = (sha256(config.compare_split) if config.compare_split else
                     sha256(config.split_manifest) if config.split_manifest.suffix.lower() == ".csv" else None)
    identifiers = Counter()
    for number, row in rows:
        if not {"publisher_case_id", "split", "ct_path", "reference_path"}.issubset(row):
            raise ManifestError("Recovered pair manifest columns are missing.")
        try:
            identifiers[case_id(row["publisher_case_id"])] += 1
        except ValueError:
            findings.add("INVALID_PAIR_ID", "Invalid pair identifier.", status="BLOCKED_MANIFEST", row=number)
    records = []
    occurrences = defaultdict(list)
    statuses = Counter()
    seen = set()
    for number, row in rows:
        summary["records"] += 1
        try:
            identifier = case_id(row["publisher_case_id"])
        except ValueError:
            continue
        if identifiers[identifier] > 1:
            findings.add("DUPLICATE_PAIR_ID", "Pair identifier occurs more than once; paths were not opened.", status="BLOCKED_MANIFEST", case_id=identifier, row=number)
            continue
        label = assignments.get(identifier)
        if label is None or row["split"].strip() != label:
            findings.add("PAIR_SPLIT_CONFLICT", "Pair assignment disagrees with the selected authoritative split.", status="BLOCKED_MANIFEST", case_id=identifier, row=number)
            continue
        if label == "Testing":
            summary["skipped_test_records"] += 1
            continue
        recorded_split_hash = row.get("split_sha256", "").strip().lower()
        if recorded_split_hash:
            if split_binding is None:
                findings.add("PAIR_SPLIT_BINDING_UNVERIFIED", "Pair manifest records a split-export hash; supply that CSV to verify the binding.", status="NOT_VERIFIED", severity="unverified", case_id=identifier)
            elif recorded_split_hash != split_binding:
                findings.add("PAIR_SPLIT_HASH_MISMATCH", "Pair manifest split-export checksum disagrees with the selected CSV.", status="BLOCKED_MANIFEST", case_id=identifier)
                continue
        seen.add(identifier)
        summary["eligible_records"] += 1
        status = row.get("readiness_status", "").strip()
        if not re.fullmatch(r"[A-Z_]{1,64}", status):
            status = "UNSPECIFIED"
        statuses[status] += 1
        record = {"case_id": identifier, "split": label, "declared_source_status": status,
                  "source_version_recorded": bool(row.get("dataset_version", "").strip()),
                  "pairing_evidence_recorded": bool(row.get("pairing_evidence", "").strip()),
                  "ct": None, "reference": None}
        if (status == "SOURCE_VERSION_UNVERIFIED" or not record["source_version_recorded"]
                or not record["pairing_evidence_recorded"] or row.get("blockers", "").strip()):
            findings.add("SOURCE_PROVENANCE_UNVERIFIED", "Source provenance or an existing declared blocker requires review.", status="NOT_VERIFIED", severity="unverified", case_id=identifier)
        paths = {}
        for role, column in [("ct", "ct_path"), ("reference", "reference_path")]:
            path = _path(row[column], config.pair_manifest.resolve().parent, roots, findings, identifier, role)
            paths[role] = path
            if path is not None:
                occurrences[os.path.normcase(str(path))].append((identifier, role))
                if _filename_id(path) not in (None, identifier):
                    findings.add("FILENAME_CASE_CONFLICT", "Recognizable source filename disagrees with manifest case ID.", status="BLOCKED_MANIFEST", case_id=identifier, role=role)
                if _filename_role(path) not in (None, role):
                    findings.add("FILENAME_ROLE_CONFLICT", "Recognizable source filename disagrees with the manifest image/mask role.", status="BLOCKED_MANIFEST", case_id=identifier, role=role)
        records.append((record, row, paths))
    for users in occurrences.values():
        if len(users) > 1:
            findings.add("DUPLICATE_SOURCE_PATH", "A resolved source path is reused across cases or roles.", status="BLOCKED_MANIFEST", uses=[{"case_id": i, "role": r} for i, r in users])
    expected = {i for i, label in assignments.items() if label in ELIGIBLE}
    if not expected:
        findings.add("NO_ELIGIBLE_CASES", "No unambiguous training/validation cases are available for readiness inspection.", status="NOT_VERIFIED", severity="unverified")
    summary["missing_pair_records"] = len(expected - seen)
    if expected - seen:
        findings.add("MISSING_PAIR_RECORDS", "Selected training/validation cases have no unambiguous pair record.", status="BLOCKED_MISSING_DATA", count=len(expected - seen))
    summary["declared_source_status_counts"] = dict(statuses)
    hashes = defaultdict(list)
    results = []
    for record, row, paths in records:
        identifier = record["case_id"]
        headers = {}
        existing = {}
        for role, path in paths.items():
            exists = path is not None and path.is_file()
            existing[role] = exists
            summary[("existing_" if exists else "missing_") + role] += 1
            if not exists:
                findings.add("MISSING_SOURCE", "CT or reference source is absent or was rejected.", status="BLOCKED_MISSING_DATA", case_id=identifier, role=role)
                record[role] = {"exists": False}
                continue
            before = _version(path)
            item = record[role] = {"exists": True, "bytes": before[0], "hash": {"status": "NOT_REQUESTED"}}
            if row.get(role + "_bytes", "").strip():
                try:
                    if int(row[role + "_bytes"]) != before[0]:
                        findings.add("SIZE_MISMATCH", "Source byte size differs from the manifest.", status="BLOCKED_INTEGRITY", case_id=identifier, role=role)
                except ValueError:
                    findings.add("INVALID_EXPECTED_SIZE", "Recorded source size is invalid.", status="BLOCKED_MANIFEST", case_id=identifier, role=role)
            if config.verify_hashes:
                try:
                    actual = sha256(path)
                    expected_hash = row.get(role + "_sha256", "").strip().lower()
                    matched = bool(re.fullmatch(r"[a-f0-9]{64}", expected_hash)) and actual == expected_hash
                    item["hash"] = {"status": "MATCH" if matched else "MISSING_EXPECTED" if not expected_hash else "MISMATCH", "actual_sha256": actual}
                    hashes[(role, actual)].append((identifier, record["split"]))
                    if not expected_hash:
                        findings.add("MISSING_EXPECTED_HASH", "No recorded SHA-256 is available for comparison.", status="NOT_VERIFIED", severity="unverified", case_id=identifier, role=role)
                    elif not matched:
                        findings.add("HASH_MISMATCH", "Source SHA-256 does not match its recorded checksum.", status="BLOCKED_INTEGRITY", case_id=identifier, role=role)
                except OSError:
                    findings.add("HASH_READ_FAILED", "Source could not be hashed.", status="BLOCKED_INTEGRITY", case_id=identifier, role=role)
            try:
                if not path.name.lower().endswith((".nii", ".nii.gz")):
                    raise ValueError("Unsupported volume format")
                info, layout = inspect_header(path)
                item["header"] = info
                headers[role] = info
                for code in info["header_issues"]:
                    findings.add(code, "NIfTI header failed a geometry or datatype check.", status="BLOCKED_GEOMETRY", case_id=identifier, role=role)
                if info["units"][0] == "unknown":
                    findings.add("UNKNOWN_SPATIAL_UNITS", "Spatial units are unknown; physical correspondence is not verified.", status="BLOCKED_GEOMETRY", severity="warning", case_id=identifier, role=role)
                if role == "reference" and config.deep_label_scan and not info["header_issues"]:
                    item["labels"] = scan_labels(path, layout)
                    if item["labels"]["status"] == "FAIL":
                        findings.add("INVALID_LABELS", "Reference contains non-finite or non-binary scaled labels.", status="BLOCKED_INTEGRITY", case_id=identifier)
                    elif item["labels"]["foreground_voxels"] == 0:
                        findings.add("EMPTY_REFERENCE", "Reference has no foreground; review the annotation contract.", status="NOT_VERIFIED", severity="warning", case_id=identifier)
            except ImportError:
                findings.add("MISSING_NIFTI_DEPENDENCY", "NiBabel/NumPy is unavailable; header and label checks were not performed.", status="NOT_VERIFIED", severity="unverified", case_id=identifier, role=role)
            except Exception:
                findings.add("INVALID_NIFTI_OR_PAYLOAD", "NIfTI header or requested label payload could not be inspected safely.", status="BLOCKED_GEOMETRY", case_id=identifier, role=role)
            try:
                if _version(path) != before:
                    findings.add("SOURCE_CHANGED", "Source changed during inspection; results are unreliable.", status="BLOCKED_INTEGRITY", case_id=identifier, role=role)
            except OSError:
                findings.add("SOURCE_CHANGED", "Source disappeared during inspection.", status="BLOCKED_INTEGRITY", case_id=identifier, role=role)
        summary["complete_pairs"] += int(all(existing.values()))
        summary["unmatched_pairs"] += int(sum(existing.values()) == 1)
        if len(headers) == 2:
            import numpy as np
            ct, reference = headers["ct"], headers["reference"]
            for code, ok in [
                ("SHAPE_MISMATCH", ct["shape"] == reference["shape"]),
                ("AFFINE_MISMATCH", np.allclose(ct["affine"], reference["affine"], rtol=0, atol=AFFINE_ATOL)),
                ("SPACING_MISMATCH", len(ct["spacing"]) == len(reference["spacing"]) and np.allclose(ct["spacing"], reference["spacing"], rtol=0, atol=SPACING_ATOL)),
            ]:
                if not ok:
                    findings.add(code, "CT/reference numerical grids disagree.", status="BLOCKED_GEOMETRY", case_id=identifier)
            units = ct["units"][0], reference["units"][0]
            if "unknown" not in units and units[0] != units[1]:
                findings.add("INCOMPATIBLE_SPATIAL_UNITS", "CT/reference spatial units disagree; no conversion was applied.", status="BLOCKED_GEOMETRY", case_id=identifier)
        results.append(record)
    for (role, _), users in hashes.items():
        if len(users) > 1:
            findings.add("DUPLICATE_CONTENT", "Identical source bytes occur in multiple cases; this is a leakage risk, not proof of patient identity.", status="BLOCKED_INTEGRITY" if role == "ct" else None, severity="error" if role == "ct" else "warning", role=role, cases=[i for i, _ in users], splits=sorted({s for _, s in users}))
    return summary, results


def _json_safe(value):
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def validate(config: Config):
    findings = Findings()
    findings.add("PATIENT_LEAKAGE_NOT_VERIFIED", "Patient/group metadata is unavailable; identifier checks do not establish absence of patient-level leakage.", severity="warning")
    report = {"schema_version": 1, "dataset": "ImageCAS", "read_only_sources": True,
              "clinical_validation": False, "automatic_dataset_approval": False,
              "split_source": {"format": config.split_manifest.suffix.lower(), "sheet": config.sheet,
                               "header_row": config.header_row if config.split_manifest.suffix.lower() == ".xlsx" else 1,
                               "id_column": config.id_column, "split_column": config.split_column},
              "checks": {"hashes_requested": config.verify_hashes, "deep_labels_requested": config.deep_label_scan,
                         "ct_voxel_values": "NOT_VERIFIED", "anatomical_registration": "NOT_VERIFIED",
                         "patient_level_leakage": "NOT_VERIFIED"},
              "geometry_policy": {"affine_atol": AFFINE_ATOL, "spacing_atol": SPACING_ATOL, "rtol": 0,
                                  "matching_grids_do_not_prove_registration": True},
              "limitations": ["No patient/group metadata: patient-level leakage cannot be declared absent.",
                              "No test-case volumes are inspected; only split metadata is used.",
                              "Header-only checks do not verify the entire voxel payload or CT intensity calibration.",
                              "READY_FOR_REVIEW is a review gate, not training approval or clinical validity."]}
    try:
        rows = read_rows(config.split_manifest, sheet=config.sheet, header_row=config.header_row)
        report["split_source"]["sha256"] = sha256(config.split_manifest)
        assignments, counts = _assignments(rows, config, findings, "selected")
        report["split"] = {"records": len(rows), "unique_unambiguous_ids": len(assignments), "counts": counts}
        if config.expected_counts is not None:
            report["split"]["expected_counts"] = config.expected_counts
            if any(counts.get(label) != count for label, count in config.expected_counts.items()):
                findings.add("SPLIT_COUNT_MISMATCH", "Actual split counts disagree with explicitly supplied expectations.", status="BLOCKED_MANIFEST")
        if config.compare_split:
            if config.compare_split.suffix.lower() != ".csv":
                raise ManifestError("The comparison source must be an explicit CSV export of the selected sheet.")
            compared, _ = _assignments(read_rows(config.compare_split), config, findings, "comparison")
            equal = assignments == compared
            report["split"]["csv_assignment_agreement"] = equal
            report["split"]["comparison_sha256"] = sha256(config.compare_split)
            if not equal:
                findings.add("SPLIT_EXPORT_MISMATCH", "Selected source and CSV export assignments disagree.", status="BLOCKED_MANIFEST")
        if config.pair_manifest:
            report["pair_source"] = {"format": config.pair_manifest.suffix.lower(), "sha256": sha256(config.pair_manifest)}
        report["pair_summary"], report["pairs"] = _pairs(config, assignments, findings)
        if not config.verify_hashes:
            findings.add("HASHES_NOT_REQUESTED", "Source checksum verification was not requested.", status="NOT_VERIFIED", severity="unverified")
        if not config.deep_label_scan:
            findings.add("LABELS_NOT_REQUESTED", "Reference payload integrity was not scanned.", status="NOT_VERIFIED", severity="unverified")
    except ManifestError as exc:
        findings.add("MANIFEST_READ_FAILED", str(exc), status="BLOCKED_MANIFEST")
    except OSError:
        findings.add("SOURCE_READ_FAILED", "Manifest or source metadata could not be read.", status="BLOCKED_MANIFEST")
    report["status"] = findings.decision()
    report["blocking_statuses"] = [status for status in STATUS_PRIORITY if any(i["blocking_status"] == status for i in findings.issues)]
    report["issues"] = findings.issues
    report["issue_counts"] = dict(Counter(i["severity"] for i in findings.issues))
    return _json_safe(report)


def _counts(text):
    try:
        parts = [part.split("=", 1) for part in text.split(",")]
        counts = {label: int(number) for label, number in parts}
        if len(counts) != len(parts) or any(k not in LABELS or v < 0 for k, v in counts.items()):
            raise ValueError
        return counts
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Use comma-separated Training=N,Val=N,Testing=N counts.") from exc


def write_report(destination, report, config):
    destination = destination.resolve()
    protected = [root.resolve() for root in config.source_roots]
    protected += [config.split_manifest.resolve().parent]
    if config.pair_manifest:
        protected.append(config.pair_manifest.resolve().parent)
    if config.compare_split:
        protected.append(config.compare_split.resolve().parent)
    if _inside(destination, protected):
        raise ValueError("Report destination is inside a protected source/manifest directory.")
    # Exclusive creation: never overwrite an existing report, symlink or source.
    with destination.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write("\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split-manifest", type=Path, required=True)
    parser.add_argument("--split-column", required=True)
    parser.add_argument("--sheet", help="Required for XLSX; never defaults to a different sheet.")
    parser.add_argument("--header-row", type=int, default=2, help="One-based XLSX header row (default: 2).")
    parser.add_argument("--id-column", default="FileName")
    parser.add_argument("--compare-split", type=Path, help="CSV export to compare with the selected source.")
    parser.add_argument("--pair-manifest", type=Path)
    parser.add_argument("--source-root", type=Path, action="append", default=[])
    parser.add_argument("--expected-counts", type=_counts, help="Optional expectations; no cohort counts are hardcoded.")
    parser.add_argument("--verify-hashes", action="store_true")
    parser.add_argument("--deep-label-scan", action="store_true", help="Explicit finite binary reference scan; never scans CT voxel values.")
    parser.add_argument("--report", type=Path, help="Create a NEW JSON report outside source/manifest directories; default stdout only.")
    args = parser.parse_args(argv)
    destination = args.report
    values = vars(args).copy()
    del values["report"]
    values["source_roots"] = tuple(values.pop("source_root"))
    config = Config(**values)
    report = validate(config)
    if destination:
        try:
            write_report(destination, report, config)
        except (OSError, ValueError):
            print("Report could not be created exclusively outside protected source directories.", file=sys.stderr)
            return 2
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0 if report["status"] == "READY_FOR_REVIEW" else 1


if __name__ == "__main__":
    raise SystemExit(main())
