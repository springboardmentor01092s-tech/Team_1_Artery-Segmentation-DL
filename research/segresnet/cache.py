"""CPU-only, source-preserving 1 mm ImageCAS Training/Val cache.

CT uses linear interpolation; categorical masks use nearest neighbour only.
Grid axes/origin are retained and the original voxel-centre extent is covered.
Unknown mask units are recorded; equal numeric affines are not registration proof.
No Testing member is opened. Outputs and provenance belong outside the repository.
"""
from __future__ import annotations

import os
for _key in ("CUDA_VISIBLE_DEVICES", "HIP_VISIBLE_DEVICES", "ROCR_VISIBLE_DEVICES"):
    os.environ[_key] = "-1"
for _key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_key] = "2"

import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil
import time

import nibabel as nib
import numpy as np
import openpyxl
import psutil
from scipy.ndimage import affine_transform


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def write_json(path, value):
    temporary = path.with_name(path.name + ".partial")
    with temporary.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def workbook_assignments(path):
    book = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        sheet = book["v2-latest"]
        headings = list(next(sheet.iter_rows(min_row=2, max_row=2, values_only=True)))
        ci, si = headings.index("FileName"), headings.index("Split-4")
        result = {}
        for row in sheet.iter_rows(min_row=3, values_only=True):
            if row[ci] is None:
                continue
            case_id = str(int(row[ci]))
            if case_id in result:
                raise ValueError("Duplicate authoritative case identifier")
            result[case_id] = row[si]
        return result
    finally:
        book.close()


def selected_rows(manifest, workbook, first=401, count=200):
    with Path(manifest).open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    by_id = {r["case_id"]: r for r in rows}
    if len(by_id) != len(rows):
        raise ValueError("Duplicate manifest case identifier")
    authority = workbook_assignments(workbook)
    training = [str(i) for i in range(first, first + count)]
    validation = sorted((r["case_id"] for r in rows if r["split"] == "Val"), key=int)
    if len(validation) != 50 or len(set(training + validation)) != count + 50:
        raise ValueError("Expected disjoint Training subset and all 50 Validation cases")
    selected = []
    for case_id in training + validation:
        r = by_id[case_id]
        expected = "Training" if case_id in training else "Val"
        if r["split"] != expected or authority.get(case_id) != expected:
            raise ValueError("Manifest/workbook split disagreement; no source opened")
        selected.append(r)
    return selected


def member_path(root, row, field):
    if row["split"] not in ("Training", "Val"):
        raise ValueError("Testing access is prohibited")
    part = Path(row[field].replace("\\", "/"))
    base = (Path(root) / row["split"]).resolve()
    path = base / part
    if part.is_absolute() or ".." in part.parts or path.is_symlink():
        raise ValueError("Unsafe source path")
    if not path.resolve().is_relative_to(base) or not path.is_file():
        raise ValueError("Unavailable or escaped source partner")
    return path


def target_grid(shape, affine):
    affine = np.asarray(affine, dtype=np.float64)
    spacing = np.linalg.norm(affine[:3, :3], axis=0)
    if not np.isfinite(affine).all() or np.any(spacing <= 0):
        raise ValueError("Invalid affine")
    directions = affine[:3, :3] / spacing
    if not np.allclose(directions.T @ directions, np.eye(3), atol=1e-6, rtol=0):
        raise ValueError("Sheared source grid is unsupported")
    grid = affine.copy()
    grid[:3, :3] = directions  # Exactly 1 mm, original axes and origin.
    dimensions = tuple((np.ceil((np.asarray(shape) - 1) * spacing).astype(int) + 1).tolist())
    return dimensions, grid


def resample(array, source_affine, output_affine, shape, order, background=0):
    transform = np.linalg.inv(source_affine) @ output_affine
    return affine_transform(array, transform[:3, :3], offset=transform[:3, 3],
                            output_shape=shape, order=order, mode="constant", cval=background,
                            prefilter=False, output=np.uint8 if order == 0 else np.float32)


def atomic_npy(path, array):
    temporary = path.with_name(path.name + ".partial")
    with temporary.open("xb") as stream:
        np.save(stream, array, allow_pickle=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def cache_case(root, output, row):
    started = time.perf_counter()
    case_id, split = row["case_id"], row["split"]
    folder = output / split / case_id
    folder.mkdir(parents=True, exist_ok=True)
    record = folder / "case.json"
    if record.exists():
        previous = json.loads(record.read_text(encoding="utf-8"))
        for file in previous["files"]:
            if digest(folder / file["name"]) != file["sha256"]:
                raise ValueError("Completed cache content changed; refusing overwrite")
        return previous
    ct_path, mask_path = (member_path(root, row, key) for key in ("ct_member", "mask_member"))
    ct, mask = nib.load(ct_path, keep_file_open=True), nib.load(mask_path, keep_file_open=True)
    if len(ct.shape) != 3 or ct.shape != mask.shape or not np.allclose(ct.affine, mask.affine, atol=1e-5, rtol=0):
        raise ValueError("CT/mask header geometry mismatch")
    if ct.header.get_xyzt_units()[0] != "mm" or int(ct.header["sform_code"]) <= 0:
        raise ValueError("Coded CT millimetre geometry required")
    shape, affine = target_grid(ct.shape, ct.affine)
    if np.prod(shape) > 32_000_000 or np.prod(ct.shape) > 180_000_000:
        raise ValueError("Declared single-case cache resource bound exceeded")
    source = {"ct_sha256": digest(ct_path), "reference_sha256": digest(mask_path)}
    categorical = np.empty(mask.shape, dtype=np.uint8)
    for z in range(0, mask.shape[2], 16):
        slab = np.asanyarray(mask.dataobj[:, :, z:z + 16])
        if not np.isfinite(slab).all() or not np.isin(slab, (0, 1)).all():
            raise ValueError("Expected the original binary lumen label 1")
        categorical[:, :, z:z + 16] = slab.astype(np.uint8)
    del slab
    if not np.any(categorical):
        raise ValueError("Empty reference annotation")
    cached_mask = resample(categorical, ct.affine, affine, shape, 0)
    if not np.any(cached_mask):
        raise ValueError("1 mm grid lost all foreground; no silent skip")
    del categorical
    image = np.asarray(ct.dataobj, dtype=np.float32)
    if not np.isfinite(image).all():
        raise ValueError("Nonfinite CT values")
    cached_image = resample(image, ct.affine, affine, shape, 1, -200)
    del image
    np.clip(cached_image, -200, 800, out=cached_image)
    cached_image += 200
    cached_image /= 1000
    atomic_npy(folder / "image.npy", cached_image.astype(np.float16))
    atomic_npy(folder / "mask.npy", cached_mask)
    files = [{"name": name, "bytes": (folder / name).stat().st_size,
              "sha256": digest(folder / name)} for name in ("image.npy", "mask.npy")]
    # Retain native Val reference bytes for native-grid, not cached-grid, scoring.
    if split == "Val":
        destination = folder / "reference-native.nii.gz"
        if destination.exists():
            raise ValueError("Unfinished native-reference output exists")
        with mask_path.open("rb") as src, destination.open("xb") as dst:
            shutil.copyfileobj(src, dst, length=1024 * 1024)
        if digest(destination) != source["reference_sha256"]:
            raise ValueError("Native reference copy differs")
        files.append({"name": destination.name, "bytes": destination.stat().st_size,
                      "sha256": source["reference_sha256"]})
    result = {"case_id": case_id, "split": split, **source, "native_shape": list(ct.shape),
              "native_affine": ct.affine.tolist(), "cache_shape": list(shape),
              "cache_affine": affine.tolist(), "native_spacing_mm": list(map(float, ct.header.get_zooms())),
              "native_orientation": list(nib.aff2axcodes(ct.affine)),
              "reference_units": mask.header.get_xyzt_units()[0],
              "spatial_assumption": "Equal CT/mask numeric geometry; CT mm affine used. Anatomical registration not independently established.",
              "target_label": 1, "cache_foreground_voxels": int(np.count_nonzero(cached_mask)),
              "seconds": time.perf_counter() - started,
              "process_rss_bytes": psutil.Process().memory_info().rss, "files": files}
    write_json(record, result)
    return result


def main():
    parser = argparse.ArgumentParser()
    for name in ("dataset-root", "manifest", "workbook", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--training-first", type=int, default=401)
    parser.add_argument("--training-count", type=int, default=200)
    args = parser.parse_args()
    rows = selected_rows(args.manifest, args.workbook, args.training_first, args.training_count)
    output = args.output.resolve()
    if output.is_relative_to(args.dataset_root.resolve()):
        raise ValueError("Cache must not modify the source dataset")
    output.mkdir(parents=True, exist_ok=True)
    recipe = {"schema_version": "imagecas-cache/1.0", "spacing_mm": [1, 1, 1], "device": "cpu",
              "ct_interpolation": "linear", "mask_interpolation": "nearest", "threshold": None,
              "ct_window_hu": [-200, 800], "image_dtype": "float16", "mask_dtype": "uint8",
              "target_label": 1, "grid_policy": "original_axes_origin_cover_voxel_centres",
              "manifest_sha256": digest(args.manifest), "workbook_sha256": digest(args.workbook),
              "sheet": "v2-latest", "split_column": "Split-4",
              "training_ids": [r["case_id"] for r in rows if r["split"] == "Training"],
              "validation_ids": [r["case_id"] for r in rows if r["split"] == "Val"]}
    identity = hashlib.sha256(canonical(recipe).encode()).hexdigest()
    recipe["recipe_sha256"] = identity
    frozen = output / "manifest.json"
    if frozen.exists():
        if json.loads(frozen.read_text(encoding="utf-8")) != recipe:
            raise ValueError("Existing cache has a different recipe")
    else:
        write_json(frozen, recipe)
    records = []
    for index, row in enumerate(rows, 1):
        if shutil.disk_usage(output).free < 4 * 1024**3:
            raise RuntimeError("Less than 4 GiB free; stopping without deleting outputs")
        result = cache_case(args.dataset_root, output, row)
        records.append(result)
        progress = {"completed": index, "expected": len(rows), "case_id": row["case_id"],
                    "split": row["split"], "seconds": round(result["seconds"], 3),
                    "cached_bytes": sum(f["bytes"] for r in records for f in r["files"])}
        write_json(output / "progress.json", progress)
        print(json.dumps(progress), flush=True)
    write_json(output / "index.json", {"complete": True, "recipe_sha256": identity,
                                       "cases": records, "training_count": args.training_count,
                                       "validation_count": 50, "testing_count": 0})


if __name__ == "__main__":
    main()
