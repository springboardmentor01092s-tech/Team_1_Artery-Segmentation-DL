"""Offline reference-only diameter profiles; no API, provider or gate registration.

ImageCAS-X VTK points are original-scan LPS millimetres, documented by the
authors in utils/precompute_centerline_samples.py. NIfTI uses RAS world axes.
All supplied polyline cells are retained. Cell order is NOT ostium direction.
Categorical nearest-neighbour planes use the component containing the supplied
point, never the largest/nearest component. This is not validated stenosis.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
from pathlib import Path
import numpy as np
import nibabel as nib
from scipy.ndimage import map_coordinates, label

NOTICE = "reference-derived research measurement, not validated"


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def vtk_polylines(path):
    """Read the fixed legacy binary POLYDATA5.1 point/line representation."""
    data = Path(path).read_bytes()
    position = 0

    def line():
        nonlocal position
        while data[position:position + 1] in (b"\r", b"\n"):
            position += 1
        end = data.index(b"\n", position)
        text = data[position:end].strip().decode("ascii")
        position = end + 1
        return text

    version, title, encoding, kind = (line() for _ in range(4))
    if "Version 5.1" not in version or encoding != "BINARY" or kind != "DATASET POLYDATA":
        raise ValueError("Unsupported VTK format; no guessed fallback")
    header = line().split()
    if header[0] != "POINTS" or header[2] not in ("float", "double"):
        raise ValueError("Expected explicit VTK points")
    count = int(header[1])
    if count < 2 or count > 100000:
        raise ValueError("Centerline point-count bound exceeded")
    dtype = np.dtype(">f4" if header[2] == "float" else ">f8")
    points = np.frombuffer(data, dtype=dtype, count=count * 3, offset=position).astype(np.float64).reshape(count, 3)
    position += count * 3 * dtype.itemsize
    header = line().split()
    if header[0] != "LINES":
        raise ValueError("Expected supplied line connectivity")
    offsets_count, connectivity_count = map(int, header[1:])
    if offsets_count < 2 or connectivity_count > 1000000:
        raise ValueError("Connectivity bound exceeded")
    if line() != "OFFSETS vtktypeint64":
        raise ValueError("Expected explicit 64-bit offsets")
    offsets = np.frombuffer(data, dtype=">i8", count=offsets_count, offset=position).astype(np.int64)
    position += offsets_count * 8
    if line() != "CONNECTIVITY vtktypeint64":
        raise ValueError("Expected explicit 64-bit connectivity")
    connectivity = np.frombuffer(data, dtype=">i8", count=connectivity_count, offset=position).astype(np.int64)
    if offsets[0] != 0 or offsets[-1] != connectivity_count or np.any(np.diff(offsets) < 2):
        raise ValueError("Invalid supplied polyline offsets")
    if not np.isfinite(points).all() or np.any(connectivity < 0) or np.any(connectivity >= count):
        raise ValueError("Invalid supplied point coordinates/indices")
    cells = [connectivity[a:b].tolist() for a, b in zip(offsets[:-1], offsets[1:])]
    return points, cells


def measure_section(mask, affine, point, tangent, radius=12., pitch=.2):
    result = {"status": "unmeasurable", "reason": None, "diameter_mm": None,
              "area_mm2": None, "foreground_pixels": 0, "other_components": None}
    length = np.linalg.norm(tangent)
    if not np.isfinite(length) or length <= 1e-8:
        result["reason"] = "undefined_tangent"
        return result
    normal = tangent / length
    axis = np.eye(3)[np.argmin(np.abs(normal))]
    u = np.cross(normal, axis)
    u /= np.linalg.norm(u)
    v = np.cross(normal, u)
    n = 2 * int(round(radius / pitch)) + 1
    if n > 257:
        raise ValueError("Reference plane dimension limit exceeded")
    grid = np.linspace(-radius, radius, n)
    aa, bb = np.meshgrid(grid, grid, indexing="ij")
    world = point[:, None, None] + u[:, None, None] * aa + v[:, None, None] * bb
    inv = np.linalg.inv(affine)
    ijk = np.einsum("ij,jkl->ikl", inv[:3, :3], world) + inv[:3, 3, None, None]
    valid = np.all((ijk >= 0) & (ijk <= (np.array(mask.shape) - 1)[:, None, None]), axis=0)
    field = map_coordinates(mask, ijk, order=0, mode="constant", cval=0, prefilter=False) > 0
    field &= valid
    components, count = label(field, structure=np.ones((3, 3), dtype=np.uint8))
    center = n // 2
    chosen = int(components[center, center])
    result["other_components"] = int(count - bool(chosen))
    if not chosen:
        result["reason"] = "supplied_centerline_outside_reference_lumen"
        return result
    selected = components == chosen
    if np.any(selected[0]) or np.any(selected[-1]) or np.any(selected[:, 0]) or np.any(selected[:, -1]):
        result["reason"] = "plane_FOV_limited"
        return result
    # Diagnostic neighbourhood test only: no morphology modifies the lumen.
    for di in (-1, 0, 1):
        for dj in (-1, 0, 1):
            if np.any(selected[1:-1, 1:-1] & ~valid[1 + di:n - 1 + di, 1 + dj:n - 1 + dj]):
                result["reason"] = "source_volume_boundary_limited"
                return result
    pixels = int(np.count_nonzero(selected))
    area = pixels * (grid[1] - grid[0])**2
    result.update(status="reference_measurement_unvalidated", foreground_pixels=pixels,
                  area_mm2=float(area), diameter_mm=float(2 * np.sqrt(area / np.pi)))
    return result


def profile_case(folder, case_id, output, source, ct_cache):
    mask_path = folder / f"{case_id}.coronary.nii.gz"
    image = nib.load(mask_path)
    if image.header.get_xyzt_units()[0] != "mm" or len(image.shape) != 3:
        raise ValueError("Explicit millimetre reference geometry required")
    original = np.asanyarray(image.dataobj)
    if not np.isfinite(original).all() or not np.isin(original, np.arange(15)).all():
        raise ValueError("Unexpected ImageCAS-X category")
    mask = original.astype(np.uint8, copy=False)
    ct_record = json.loads((ct_cache / "Training" / case_id / "case.json").read_text(encoding="utf-8"))
    if list(image.shape) != ct_record["native_shape"] or not np.allclose(image.affine, ct_record["native_affine"], rtol=0, atol=1e-5):
        raise ValueError("Reference and identified original CT numeric geometry differ")
    allowed_files = {r["file"]: r["sha256"] for r in source["files"] if r["case_id"] == case_id}
    if sha(mask_path) != allowed_files[mask_path.name]:
        raise ValueError("Reference mask identity differs")
    records, branches = [], []
    for side in ("left", "right"):
        centerline = folder / f"{case_id}.coronary_{side}_centerline.vtk"
        if sha(centerline) != allowed_files[centerline.name]:
            raise ValueError("Centerline identity differs")
        lps, cells = vtk_polylines(centerline)
        ras = lps * np.array([-1., -1., 1.])
        for cell_index, ids in enumerate(cells):
            points = ras[ids]
            segments = np.linalg.norm(np.diff(points, axis=0), axis=1)
            if np.any(segments <= 1e-8):
                raise ValueError("Repeated consecutive coordinates; no invented tangent")
            arc = np.r_[0., np.cumsum(segments)]
            tangents = np.gradient(points, axis=0)
            branch = f"{side}-{cell_index}"
            branches.append({"branch": branch, "point_ids": ids, "points_ras_mm": points.tolist(),
                             "orientation": "supplied_cell_order_not_assumed_proximal"})
            for index, (point_id, point, tangent) in enumerate(zip(ids, points, tangents)):
                result = measure_section(mask, image.affine, point, tangent)
                records.append({"dataset_case_id": case_id, "side": side, "branch": branch,
                                "point_id": point_id, "s_mm": float(arc[index]),
                                "ras_x_mm": float(point[0]), "ras_y_mm": float(point[1]),
                                "ras_z_mm": float(point[2]), **result})
    path = output / f"{case_id}-profile.csv"
    with path.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    geometry = {"shape": list(image.shape), "affine_ras_mm": image.affine.tolist(),
                "mask_sha256": sha(mask_path), "branches": branches}
    (output / f"{case_id}-geometry.json").write_text(json.dumps(geometry), encoding="utf-8")
    return records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ct-cache", type=Path, required=True)
    args = parser.parse_args()
    source = json.loads((args.input / "provenance.json").read_text(encoding="utf-8"))
    if source["license"] != "CC-BY-4.0" or any(r["split"] != "Training" for r in source["files"]):
        raise ValueError("Approved reference Training provenance required")
    args.output.mkdir(parents=True, exist_ok=False)
    rows = []
    for case in source["cases"]:
        rows.extend(profile_case(args.input, case, args.output, source, args.ct_cache))
    result = {"schema_version": "reference-diameter-profile/0.1", "notice": NOTICE,
              "mask_origin": "reference_annotation", "validation_status": "unvalidated",
              "uncertainty_status": "not_estimated", "gate_registration": "pending_explicit_approval",
              "method": "nearest-neighbour orthogonal plane; 8-connected origin component; 2*sqrt(area/pi)",
              "plane_radius_mm": 12, "pixel_pitch_mm": .2,
              "reference_provenance": source, "sections": rows,
              "limitations": ["reference annotation is not model prediction", "no stenosis percentage, severity or clinical confidence", "supplied cell order is not assumed proximal", "finite raster and tangent effects; no calibrated uncertainty or validated resolution gate", "no smoothing, hole filling, nearest/largest component selection or silent exclusion"]}
    (args.output / "profiles.json").write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"cases": source["cases"], "sections": len(rows),
                      "measured_unvalidated": sum(r["diameter_mm"] is not None for r in rows),
                      "unmeasurable": sum(r["diameter_mm"] is None for r in rows),
                      "gate_registered": False}))


if __name__ == "__main__":
    main()
