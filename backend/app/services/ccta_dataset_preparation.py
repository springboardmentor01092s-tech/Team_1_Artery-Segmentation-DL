"""Offline CCTA dataset registration and validation.

This module only inventories source assets and emits a manifest. It never
rewrites or resamples image data, infers lesion labels, or connects to the
application database. Dataset-specific layouts and label semantics must be
confirmed from the downloaded dataset documentation before registration.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np

MANIFEST_SCHEMA = "vascuai-ccta-dataset/0.1"
PREPROCESSING_SCHEMA = "vascuai-ccta-preprocessing/0.1"
DATASET_FAMILIES = {"imagecas", "imagecas_x", "asoca", "future_ccta"}
ASSET_KINDS = {"image", "vessel_mask", "centerline", "mesh", "lesion_annotation", "other_annotation"}
SPLITS = {"train", "validation", "test", "unassigned"}
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_MAX_JSON_BYTES = 8 * 1024 * 1024
_MAX_LABEL_VALUES = 256
_MAX_NRRD_LABEL_SCAN_BYTES = 256 * 1024 * 1024


class DatasetPreparationError(ValueError):
    """Safe, non-sensitive dataset registration/validation error."""


@dataclass(frozen=True)
class Geometry:
    dimensions: tuple[int, int, int]
    affine: tuple[tuple[float, float, float, float], ...]
    spacing: tuple[float, float, float]
    spatial_units: str
    coordinate_frame: str
    axis_order: str
    orientation: tuple[str, str, str] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "dimensions": list(self.dimensions),
            "affine": [list(row) for row in self.affine],
            "voxel_spacing": list(self.spacing),
            "spatial_units": self.spatial_units,
            "coordinate_frame": self.coordinate_frame,
            "axis_order": self.axis_order,
            "orientation": list(self.orientation) if self.orientation else None,
        }

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(self.as_dict())


def canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                          allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise DatasetPreparationError("Manifest contains non-JSON or non-finite values") from exc


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _safe_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise DatasetPreparationError(f"Invalid de-identified {label}")
    return value


def _finite_matrix(value: Any) -> np.ndarray:
    matrix = np.asarray(value, dtype=np.float64)
    if matrix.shape != (4, 4) or not np.isfinite(matrix).all():
        raise DatasetPreparationError("Image geometry affine is invalid")
    if not np.allclose(matrix[3], [0, 0, 0, 1], atol=1e-8, rtol=0):
        raise DatasetPreparationError("Image geometry affine is not homogeneous")
    scaled = matrix[:3, :3] / np.maximum(np.max(np.abs(matrix[:3, :3]), axis=0), 1e-300)
    if abs(float(np.linalg.det(scaled))) < 1e-8:
        raise DatasetPreparationError("Image geometry affine is singular or ill-conditioned")
    return matrix


def geometry_from_parts(dimensions: Any, affine: Any, units: str, frame: str,
                        axis_order: str, orientation: Any = None) -> Geometry:
    dims = tuple(int(v) for v in dimensions)
    if len(dims) != 3 or any(v < 1 or v > 1024 for v in dims) or math.prod(dims) > 134_217_728:
        raise DatasetPreparationError("3D spatial dimensions exceed supported bounds")
    a = _finite_matrix(affine)
    spacing = tuple(float(v) for v in np.linalg.norm(a[:3, :3], axis=0))
    if any(not math.isfinite(v) or v <= 0 for v in spacing):
        raise DatasetPreparationError("Image voxel spacing must be finite and positive")
    if not isinstance(units, str) or not units.strip() or not isinstance(frame, str) or not frame.strip():
        raise DatasetPreparationError("Image spatial units and coordinate frame are required")
    orient = tuple(str(v) for v in orientation) if orientation is not None else None
    if orient is not None and len(orient) != 3:
        raise DatasetPreparationError("Image orientation must describe three axes")
    return Geometry(dims, tuple(tuple(float(x) for x in row) for row in a), spacing,
                    units.strip(), frame.strip(), axis_order, orient)


def _nifti_geometry(path: Path) -> Geometry:
    from app.services.volume_ingestion import validate_nifti_file
    import nibabel as nib

    ext = ".nii.gz" if path.name.lower().endswith(".nii.gz") else path.suffix.lower()
    props = validate_nifti_file(path, ext)
    if props.ndim != 3:
        raise DatasetPreparationError("Dataset images and voxel annotations must be 3D")
    image = nib.load(str(path), mmap=True)
    affine = np.asarray(image.affine, dtype=float)
    units = image.header.get_xyzt_units()[0] or "unknown"
    try:
        orientation = tuple(nib.aff2axcodes(affine))
    except Exception:
        orientation = None
    return geometry_from_parts(props.shape, affine, units, "RAS", "nifti_i_j_k", orientation)


def _nrrd_geometry(path: Path) -> Geometry:
    try:
        import nrrd  # type: ignore[import-not-found]
    except ImportError as exc:
        raise DatasetPreparationError("NRRD support requires the optional pynrrd package") from exc
    try:
        header = nrrd.read_header(str(path), index_order="F")
        sizes = tuple(int(v) for v in header["sizes"])
        dirs = header["space directions"]
        origin = np.asarray(header["space origin"], dtype=float)
        space = str(header.get("space", "unknown"))
        units = header.get("space units")
        if len(sizes) != 3 or len(dirs) != 3 or origin.shape != (3,):
            raise DatasetPreparationError("NRRD must declare three spatial axes and an origin")
        linear = np.column_stack([np.asarray(v, dtype=float) for v in dirs])
        affine = np.eye(4, dtype=float)
        affine[:3, :3] = linear
        affine[:3, 3] = origin
        spatial_units = ",".join(str(v) for v in units) if units else "unknown"
        frame = "LPS" if "left-posterior" in space.lower() else "RAS" if "right-anterior" in space.lower() else space
        return geometry_from_parts(sizes, affine, spatial_units, frame, "nrrd_index_order_F")
    except DatasetPreparationError:
        raise
    except Exception as exc:
        raise DatasetPreparationError("NRRD header or geometry is invalid") from exc


def _dicom_series_geometry(path: Path) -> tuple[Geometry, list[dict[str, Any]]]:
    try:
        import pydicom  # type: ignore[import-not-found]
    except ImportError as exc:
        raise DatasetPreparationError("DICOM support requires the optional pydicom package") from exc
    files = [path] if path.is_file() else sorted(p for p in path.iterdir() if p.is_file())
    if not files:
        raise DatasetPreparationError("DICOM series contains no files")
    records = []
    try:
        for file in files:
            if file.is_symlink():
                raise DatasetPreparationError("DICOM asset may not contain symlinks")
            ds = pydicom.dcmread(str(file), stop_before_pixels=True, force=False)
            if not all(hasattr(ds, k) for k in ("SeriesInstanceUID", "SOPInstanceUID", "Rows", "Columns",
                                                 "ImagePositionPatient", "ImageOrientationPatient", "PixelSpacing",
                                                 "Modality", "BitsAllocated", "BitsStored", "PixelRepresentation",
                                                 "PhotometricInterpretation")):
                raise DatasetPreparationError("DICOM object is missing required image geometry tags")
            if ds.Modality != "CT":
                raise DatasetPreparationError("Only DICOM CT image series are supported")
            if int(getattr(ds, "NumberOfFrames", 1)) != 1:
                raise DatasetPreparationError("Enhanced/multiframe DICOM requires a separately reviewed adapter")
            orientation = np.asarray(ds.ImageOrientationPatient, dtype=float)
            position = np.asarray(ds.ImagePositionPatient, dtype=float)
            pixel = np.asarray(ds.PixelSpacing, dtype=float)
            if orientation.shape != (6,) or position.shape != (3,) or pixel.shape != (2,) or not np.isfinite(np.r_[orientation, position, pixel]).all() or np.any(pixel <= 0):
                raise DatasetPreparationError("DICOM image geometry tags are invalid")
            records.append({"path": file, "series": str(ds.SeriesInstanceUID), "sop": str(ds.SOPInstanceUID),
                            "rows": int(ds.Rows), "columns": int(ds.Columns), "position": position,
                            "orientation": orientation, "pixel": pixel,
                            "bits_allocated": int(getattr(ds, "BitsAllocated", 0)),
                            "bits_stored": int(getattr(ds, "BitsStored", 0)),
                            "pixel_representation": int(getattr(ds, "PixelRepresentation", 0)),
                            "rescale_slope": float(getattr(ds, "RescaleSlope", 1.0)),
                            "rescale_intercept": float(getattr(ds, "RescaleIntercept", 0.0)),
                            "photometric_interpretation": str(getattr(ds, "PhotometricInterpretation", ""))})
    except DatasetPreparationError:
        raise
    except Exception as exc:
        raise DatasetPreparationError("DICOM series could not be read safely") from exc
    series = {r["series"] for r in records}
    sops = [r["sop"] for r in records]
    if len(series) != 1 or len(set(sops)) != len(sops):
        raise DatasetPreparationError("DICOM directory must contain one series without duplicate instances")
    first = records[0]
    if any(r["rows"] != first["rows"] or r["columns"] != first["columns"] or
           not np.allclose(r["orientation"], first["orientation"], atol=1e-5, rtol=0) or
           not np.allclose(r["pixel"], first["pixel"], atol=1e-5, rtol=0) or
           any(r[key] != first[key] for key in ("bits_allocated", "bits_stored", "pixel_representation", "photometric_interpretation")) or
           not math.isclose(r["rescale_slope"], first["rescale_slope"], abs_tol=1e-8) or
           not math.isclose(r["rescale_intercept"], first["rescale_intercept"], abs_tol=1e-8) for r in records):
        raise DatasetPreparationError("DICOM instances have inconsistent dimensions, orientation, or pixel mapping")
    if not math.isfinite(first["rescale_slope"]) or not math.isfinite(first["rescale_intercept"]):
        raise DatasetPreparationError("DICOM rescale mapping is invalid")
    if (first["bits_allocated"] not in {8, 16, 32} or not 1 <= first["bits_stored"] <= first["bits_allocated"]
            or first["pixel_representation"] not in {0, 1}
            or first["photometric_interpretation"] not in {"MONOCHROME1", "MONOCHROME2"}):
        raise DatasetPreparationError("DICOM CT pixel representation metadata is unsupported")
    row_direction = first["orientation"][:3]
    column_direction = first["orientation"][3:]
    if not np.isclose(np.linalg.norm(row_direction), 1, atol=1e-4) or not np.isclose(np.linalg.norm(column_direction), 1, atol=1e-4) or not np.isclose(np.dot(row_direction, column_direction), 0, atol=1e-4):
        raise DatasetPreparationError("DICOM direction cosines are not orthonormal")
    normal = np.cross(row_direction, column_direction)
    records.sort(key=lambda r: float(np.dot(r["position"], normal)))
    projections = np.asarray([np.dot(r["position"], normal) for r in records], dtype=float)
    if len(records) > 1:
        differences = np.diff(projections)
        if np.any(differences <= 1e-5) or not np.allclose(differences, np.median(differences), atol=0.05, rtol=0.02):
            raise DatasetPreparationError("DICOM slice positions are duplicated or irregular")
        slice_spacing = float(np.median(differences))
    else:
        # A single-slice image lacks through-plane spacing; do not invent it.
        raise DatasetPreparationError("DICOM requires at least two slices to establish slice spacing")
    affine = np.eye(4, dtype=float)
    affine[:3, 0] = row_direction * float(first["pixel"][1])
    affine[:3, 1] = column_direction * float(first["pixel"][0])
    affine[:3, 2] = normal * slice_spacing
    affine[:3, 3] = records[0]["position"]
    geom = geometry_from_parts((first["columns"], first["rows"], len(records)), affine,
                               "mm", "LPS", "dicom_column_row_slice")
    return geom, [{"path": r["path"], "sop_instance_uid": r["sop"]} for r in records]


def inspect_image(path: str | Path, declared_format: str | None = None) -> tuple[Geometry, dict[str, Any]]:
    """Read image headers only; return native geometry and a stable asset digest."""
    source = Path(path)
    if source.is_symlink():
        raise DatasetPreparationError("Symlinked dataset assets are not accepted")
    if not source.exists():
        raise DatasetPreparationError("Dataset image asset does not exist")
    fmt = (declared_format or ("dicom" if source.is_dir() else "nifti" if source.name.lower().endswith((".nii", ".nii.gz")) else source.suffix.lower().lstrip("."))).lower()
    if fmt in {"nii", "nii.gz", "nifti", "nifti1", "nifti2"}:
        if not source.is_file():
            raise DatasetPreparationError("NIfTI asset must be a file")
        try:
            geom = _nifti_geometry(source)
        except Exception as exc:
            if isinstance(exc, DatasetPreparationError):
                raise
            raise DatasetPreparationError("NIfTI image header or payload validation failed") from exc
        return geom, {"format": "nifti", "sha256": _file_sha256(source), "size_bytes": source.stat().st_size}
    if fmt in {"nrrd", "nhdr"}:
        if not source.is_file():
            raise DatasetPreparationError("NRRD asset must be a file")
        if source.suffix.lower() == ".nhdr":
            raise DatasetPreparationError("Detached NRRD header/payload pairs require a composite-asset adapter")
        geom = _nrrd_geometry(source)
        return geom, {"format": "nrrd", "sha256": _file_sha256(source), "size_bytes": source.stat().st_size}
    if fmt in {"dcm", "dicom"}:
        geom, instances = _dicom_series_geometry(source)
        digest = hashlib.sha256()
        total = 0
        for item in instances:
            file = item["path"]
            rel_name = file.name.encode("utf-8")
            digest.update(len(rel_name).to_bytes(4, "big")); digest.update(rel_name)
            file_hash = _file_sha256(file)
            digest.update(bytes.fromhex(file_hash)); total += file.stat().st_size
        return geom, {"format": "dicom_series", "sha256": digest.hexdigest(), "size_bytes": total,
                      "instance_count": len(instances),
                      "instance_order": "ascending projection on DICOM slice normal",
                      "pixel_mapping": _dicom_pixel_mapping(source)}
    raise DatasetPreparationError("Unsupported imaging format; expected NIfTI, NRRD, or DICOM series")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _dicom_pixel_mapping(path: Path) -> dict[str, Any]:
    """Return non-identifying intensity mapping metadata for the verified series."""
    import pydicom  # type: ignore[import-not-found]
    files = [path] if path.is_file() else sorted(p for p in path.iterdir() if p.is_file())
    ds = pydicom.dcmread(str(files[0]), stop_before_pixels=True, force=False)
    return {"bits_allocated": int(getattr(ds, "BitsAllocated", 0)),
            "bits_stored": int(getattr(ds, "BitsStored", 0)),
            "pixel_representation": int(getattr(ds, "PixelRepresentation", 0)),
            "rescale_slope": float(getattr(ds, "RescaleSlope", 1.0)),
            "rescale_intercept": float(getattr(ds, "RescaleIntercept", 0.0)),
            "photometric_interpretation": str(getattr(ds, "PhotometricInterpretation", ""))}


def _safe_asset_path(root: Path, relative: Any) -> Path:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise DatasetPreparationError("Asset path must be relative to the dataset root")
    if "\\" in relative:
        raise DatasetPreparationError("Asset paths must use portable forward slashes")
    candidate = root / relative
    if any(part in {".", ".."} for part in Path(relative).parts):
        raise DatasetPreparationError("Asset path traversal is not allowed")
    try:
        resolved_root = root.resolve(strict=True)
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(resolved_root)
    except (OSError, ValueError) as exc:
        raise DatasetPreparationError("Asset path is missing or outside the dataset root") from exc
    current = candidate
    while current != root and current != current.parent:
        if current.is_symlink():
            raise DatasetPreparationError("Symlinked dataset assets are not accepted")
        current = current.parent
    if not resolved.is_file() and not resolved.is_dir():
        raise DatasetPreparationError("Asset path has an unsupported filesystem type")
    return resolved


def _compare_geometry(reference: Geometry, candidate: Geometry, label: str) -> str:
    if reference.dimensions != candidate.dimensions:
        raise DatasetPreparationError(f"{label} dimensions do not align with the source image")
    if reference.coordinate_frame != candidate.coordinate_frame:
        raise DatasetPreparationError(f"{label} coordinate frame does not align with the source image")
    if not np.allclose(reference.affine, candidate.affine, atol=1e-5, rtol=1e-7):
        raise DatasetPreparationError(f"{label} affine does not align with the source image")
    if reference.spatial_units == candidate.spatial_units:
        return "verified_shape_affine_frame_units"
    if "unknown" in {reference.spatial_units, candidate.spatial_units}:
        return "shape_affine_frame_verified_units_unresolved"
    raise DatasetPreparationError(f"{label} coordinate units do not align with the source image")


def _scan_label_values(path: Path, fmt: str, geometry: Geometry) -> set[int]:
    """Read discrete mask labels in native order and compare with declaration."""
    normalized = fmt.lower() if fmt else ("nifti" if path.name.lower().endswith((".nii", ".nii.gz")) else path.suffix.lower().lstrip("."))
    observed: set[int] = set()
    if normalized in {"nii", "nii.gz", "nifti", "nifti1", "nifti2"}:
        import nibabel as nib
        proxy = nib.load(str(path), mmap=True).dataobj
        for index in range(geometry.dimensions[2]):
            plane = np.asarray(proxy[:, :, index])
            if not np.isfinite(plane).all() or not np.equal(plane, np.floor(plane)).all():
                raise DatasetPreparationError("Vessel mask contains non-finite or non-integer label values")
            observed.update(int(v) for v in np.unique(plane))
            if len(observed) > _MAX_LABEL_VALUES:
                raise DatasetPreparationError("Vessel mask has too many distinct values for a declared label schema")
    elif normalized in {"nrrd", "nhdr"}:
        try:
            import nrrd  # type: ignore[import-not-found]
        except ImportError as exc:
            raise DatasetPreparationError("NRRD label-map validation requires the optional pynrrd package") from exc
        try:
            header = nrrd.read_header(str(path), index_order="F")
            sizes = tuple(int(v) for v in header["sizes"])
            type_bytes = {"uchar": 1, "unsigned char": 1, "uint8": 1, "char": 1,
                          "short": 2, "short int": 2, "int16": 2, "ushort": 2,
                          "unsigned short": 2, "uint16": 2, "int": 4, "int32": 4,
                          "uint": 4, "uint32": 4, "float": 4, "double": 8,
                          "int64": 8, "uint64": 8}.get(str(header.get("type", "")).lower())
            if len(sizes) != 3 or type_bytes is None or math.prod(sizes) * type_bytes > _MAX_NRRD_LABEL_SCAN_BYTES:
                raise DatasetPreparationError("NRRD mask exceeds bounded label-validation capacity or has unsupported scalar type")
            data, _ = nrrd.read(str(path), index_order="F")
            if data.shape != geometry.dimensions or not np.isfinite(data).all() or not np.equal(data, np.floor(data)).all():
                raise DatasetPreparationError("NRRD vessel mask dimensions or discrete labels are invalid")
            observed = {int(v) for v in np.unique(data)}
        except DatasetPreparationError:
            raise
        except Exception as exc:
            raise DatasetPreparationError("NRRD label-map payload could not be validated") from exc
    else:
        raise DatasetPreparationError("Vessel masks must be NIfTI or NRRD; DICOM SEG needs a separately reviewed adapter")
    if not observed:
        raise DatasetPreparationError("Vessel mask contains no label values")
    return observed


def _validate_label_schema(schema: Any, observed: set[int]) -> dict[str, Any]:
    if not isinstance(schema, dict) or set(schema) != {"schema_version", "labels"} or schema["schema_version"] != "vascuai-label-map/0.1":
        raise DatasetPreparationError("Vessel masks require a versioned label schema")
    labels = schema["labels"]
    if not isinstance(labels, list) or not labels or len(labels) > _MAX_LABEL_VALUES:
        raise DatasetPreparationError("Vessel mask label schema is empty or too large")
    declared: dict[int, str] = {}
    for item in labels:
        if not isinstance(item, dict) or set(item) != {"value", "meaning"} or type(item["value"]) is not int or item["value"] < 0 or not isinstance(item["meaning"], str) or not item["meaning"].strip():
            raise DatasetPreparationError("Label schema entries require unique integer values and documented meanings")
        if item["value"] in declared:
            raise DatasetPreparationError("Vessel mask label schema contains duplicate values")
        declared[item["value"]] = item["meaning"]
    if observed != set(declared):
        raise DatasetPreparationError("Observed vessel mask labels do not match the declared label schema")
    if declared.get(0, "").lower() not in {"background", "background/none"}:
        raise DatasetPreparationError("Vessel mask schema must explicitly define zero as background")
    return {"schema_version": schema["schema_version"],
            "labels": [{"value": key, "meaning": declared[key]} for key in sorted(declared)],
            "observed_values": sorted(observed)}


def _validate_mesh(path: Path, geometry: Geometry, metadata: dict[str, Any]) -> dict[str, Any]:
    """Validate vertex bounds for ASCII OBJ/PLY without altering coordinates."""
    if path.stat().st_size > 64 * 1024 * 1024:
        raise DatasetPreparationError("Mesh exceeds the bounded ASCII mesh validation size")
    if metadata.get("geometry_fingerprint") != geometry.fingerprint:
        raise DatasetPreparationError("Mesh geometry fingerprint does not match source image")
    coordinate_space = metadata.get("coordinate_space")
    frame, units = metadata.get("coordinate_frame"), metadata.get("spatial_units")
    if coordinate_space not in {"native_ijk", "physical"}:
        raise DatasetPreparationError("Mesh coordinate space must be explicit")
    if coordinate_space == "physical" and (frame != geometry.coordinate_frame or units != geometry.spatial_units):
        raise DatasetPreparationError("Mesh coordinate frame or units do not match source image")
    vertices: list[list[float]] = []
    try:
        if path.suffix.lower() == ".obj":
            for line in path.read_text(encoding="utf-8").splitlines():
                fields = line.strip().split()
                if fields and fields[0] == "v":
                    vertices.append([float(value) for value in fields[1:4]])
        elif path.suffix.lower() == ".ply":
            rows = path.read_text(encoding="ascii").splitlines()
            if not rows or rows[0].strip() != "ply" or "format ascii 1.0" not in rows:
                raise DatasetPreparationError("Only ASCII PLY meshes are supported")
            end = rows.index("end_header")
            count = next(int(row.split()[2]) for row in rows[:end] if row.startswith("element vertex "))
            element_index = next(i for i, row in enumerate(rows[:end]) if row.startswith("element vertex "))
            property_names = []
            for row in rows[element_index + 1:end]:
                parts = row.split()
                if parts and parts[0] == "element":
                    break
                if parts and parts[0] == "property":
                    if parts[1] == "list" or len(parts) != 3:
                        raise DatasetPreparationError("PLY vertex properties must be scalar values")
                    property_names.append(parts[2])
            if not all(axis in property_names for axis in ("x", "y", "z")):
                raise DatasetPreparationError("PLY vertex properties must include x, y, and z")
            axes = [property_names.index(axis) for axis in ("x", "y", "z")]
            if len(rows) < end + 1 + count:
                raise DatasetPreparationError("PLY vertex data is truncated")
            vertices = [[float(rows[i].split()[axis]) for axis in axes] for i in range(end + 1, end + 1 + count)]
        else:
            raise DatasetPreparationError("Mesh validation currently supports ASCII OBJ and PLY")
    except DatasetPreparationError:
        raise
    except Exception as exc:
        raise DatasetPreparationError("Mesh vertex data is malformed") from exc
    points = np.asarray(vertices, dtype=float)
    if points.ndim != 2 or points.shape[1] != 3 or not len(points) or not np.isfinite(points).all():
        raise DatasetPreparationError("Mesh must contain finite 3D vertices")
    if coordinate_space == "physical":
        inv = np.linalg.inv(np.asarray(geometry.affine, dtype=float))
        points = (inv @ np.c_[points, np.ones(len(points))].T).T[:, :3]
    maximum = np.asarray(geometry.dimensions, dtype=float) - 1
    if np.any(points < -1e-5) or np.any(points > maximum + 1e-5):
        raise DatasetPreparationError("Mesh vertex lies outside source image geometry")
    return {"vertex_count": int(len(points)), "coordinate_space": coordinate_space,
            "geometry_fingerprint": geometry.fingerprint, "alignment": "verified_vertex_bounds"}


def _validate_preprocessing(config: Any) -> dict[str, Any]:
    if not isinstance(config, dict) or config.get("schema_version") != PREPROCESSING_SCHEMA:
        raise DatasetPreparationError("A versioned preprocessing configuration is required")
    allowed = {"schema_version", "orientation_policy", "target_spacing", "target_spacing_units", "resampling", "image_interpolation",
               "mask_interpolation", "intensity_transform", "crop_policy", "software_versions", "seed"}
    if set(config) != allowed:
        raise DatasetPreparationError("Preprocessing configuration is incomplete or has unsupported fields")
    if (type(config["seed"]) is not int or not isinstance(config["software_versions"], dict)
            or not config["software_versions"] or any(not isinstance(k, str) or not isinstance(v, str) for k, v in config["software_versions"].items())
            or not isinstance(config["intensity_transform"], dict) or not isinstance(config["crop_policy"], (str, dict))):
        raise DatasetPreparationError("Preprocessing seed, software versions, intensity, or crop policy is invalid")
    if config.get("orientation_policy") != "preserve_native":
        raise DatasetPreparationError("Dataset preparation requires preserve_native orientation policy")
    if config.get("resampling") not in {"none", "explicit"}:
        raise DatasetPreparationError("Resampling must be explicitly set to none or explicit")
    if config.get("resampling") == "none" and config.get("target_spacing") is not None:
        raise DatasetPreparationError("Target spacing must be null when resampling is disabled")
    if config.get("resampling") == "none" and config.get("target_spacing_units") is not None:
        raise DatasetPreparationError("Target spacing units must be null when resampling is disabled")
    if config.get("resampling") == "explicit":
        spacing = config.get("target_spacing")
        if not isinstance(spacing, list) or len(spacing) != 3 or any(type(v) not in (float, int) or not math.isfinite(v) or v <= 0 for v in spacing):
            raise DatasetPreparationError("Explicit resampling requires three positive finite target spacings")
        if config.get("target_spacing_units") not in {"mm", "cm", "m", "micron"}:
            raise DatasetPreparationError("Explicit target spacing units must be declared")
        if config.get("image_interpolation") not in {"linear", "bspline", "nearest"} or config.get("mask_interpolation") not in {"nearest", "label_gaussian"}:
            raise DatasetPreparationError("Resampling interpolation policies must be explicit")
    return json.loads(canonical_json(config))


def _read_json_asset(path: Path) -> dict[str, Any]:
    if path.stat().st_size > _MAX_JSON_BYTES:
        raise DatasetPreparationError("Structured annotation exceeds the size limit")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DatasetPreparationError("Structured annotation is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise DatasetPreparationError("Structured annotation root must be an object")
    return value


def _validate_structured_annotation(path: Path, kind: str, image_geometry: Geometry) -> dict[str, Any]:
    doc = _read_json_asset(path)
    expected_schema = {"centerline": "vascuai-centerline/0.1", "lesion_annotation": "vascuai-lesion-annotation/0.1"}.get(kind)
    if expected_schema is None or doc.get("schema_version") != expected_schema:
        raise DatasetPreparationError(f"{kind} requires the documented versioned JSON schema")
    common = {"schema_version", "geometry_fingerprint", "coordinate_space", "coordinate_frame", "spatial_units"}
    top_allowed = common | ({"points"} if kind == "centerline" else {"lesions", "protocol_ref", "label_semantics_ref"})
    if set(doc) - top_allowed:
        raise DatasetPreparationError(f"{kind} contains unsupported or unreviewed fields")
    if kind == "lesion_annotation" and (not isinstance(doc.get("protocol_ref"), str) or not doc["protocol_ref"].strip()):
        raise DatasetPreparationError("Lesion annotation requires its source protocol reference")
    if doc.get("geometry_fingerprint") != image_geometry.fingerprint:
        raise DatasetPreparationError(f"{kind} geometry fingerprint does not match source image")
    coordinate_space = doc.get("coordinate_space")
    if coordinate_space not in {"native_ijk", "physical"}:
        raise DatasetPreparationError(f"{kind} coordinate space must be explicit")
    if coordinate_space == "physical" and (doc.get("coordinate_frame") != image_geometry.coordinate_frame or doc.get("spatial_units") != image_geometry.spatial_units):
        raise DatasetPreparationError(f"{kind} physical coordinate frame or units do not match source image")
    entries = doc.get("points" if kind == "centerline" else "lesions")
    if not isinstance(entries, list) or not entries:
        raise DatasetPreparationError(f"{kind} contains no coordinate entries")
    ids = set()
    inverse = np.linalg.inv(np.asarray(image_geometry.affine, dtype=float))

    def check_coord(value: Any, field: str) -> list[float]:
        coord = np.asarray(value, dtype=float)
        if coord.shape != (3,) or not np.isfinite(coord).all():
            raise DatasetPreparationError(f"{kind} has an invalid {field} coordinate")
        if coordinate_space == "native_ijk":
            ijk = coord
        else:
            ijk = (inverse @ np.r_[coord, 1.0])[:3]
        if np.any(ijk < -1e-5) or np.any(ijk > np.asarray(image_geometry.dimensions, dtype=float) - 1 + 1e-5):
            raise DatasetPreparationError(f"{kind} coordinate lies outside source image geometry")
        return [float(v) for v in coord]

    for entry in entries:
        if not isinstance(entry, dict):
            raise DatasetPreparationError(f"{kind} entries must be objects")
        allowed_entry = ({"id", "ijk", "point", "branch_id", "sequence_index"} if kind == "centerline" else
                         {"id", "center_ijk", "proximal_boundary_ijk", "distal_boundary_ijk", "center", "proximal_boundary", "distal_boundary", "artery", "segment", "location_description", "minimum_lumen_diameter", "reference_diameter", "measurement_units", "measurement_method", "percentage_narrowing", "severity_category", "annotation_source", "evidence_ref", "unavailable_reason"})
        if set(entry) - allowed_entry:
            raise DatasetPreparationError(f"{kind} entry contains unsupported or unreviewed fields")
        item_id = _safe_id(entry.get("id"), f"{kind} entry identifier")
        if item_id in ids:
            raise DatasetPreparationError(f"{kind} contains duplicate entry identifiers")
        ids.add(item_id)
        if kind == "centerline" and "branch_id" in entry:
            _safe_id(entry["branch_id"], "centerline branch ID")
        if kind == "centerline" and "sequence_index" in entry and (type(entry["sequence_index"]) is not int or entry["sequence_index"] < 0):
            raise DatasetPreparationError("Centerline sequence_index must be a non-negative integer")
        fields = ["ijk"] if kind == "centerline" else ["center", "proximal_boundary", "distal_boundary"]
        for field in fields:
            coord_key = (("point" if coordinate_space == "physical" else "ijk") if kind == "centerline"
                         else (field if coordinate_space == "physical" else f"{field}_ijk"))
            if coord_key not in entry:
                raise DatasetPreparationError(f"{kind} is missing required coordinate {coord_key}")
            check_coord(entry[coord_key], coord_key)
        if kind == "lesion_annotation":
            # Preserve source-provided labels only. This tool never derives or
            # upgrades annotation values to expert/clinical ground truth.
            for field in ("minimum_lumen_diameter", "reference_diameter", "percentage_narrowing"):
                value = entry.get(field)
                if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or value < 0):
                    raise DatasetPreparationError(f"{field} must be a finite non-negative source value or null")
            percentage = entry.get("percentage_narrowing")
            if percentage is not None and percentage > 100:
                raise DatasetPreparationError("percentage_narrowing must be between zero and 100 or null")
            if entry.get("severity_category") is not None and not isinstance(entry["severity_category"], str):
                raise DatasetPreparationError("Source severity category must be a string or null")
            if any(entry.get(field) is not None for field in ("minimum_lumen_diameter", "reference_diameter", "percentage_narrowing", "severity_category")):
                if not isinstance(entry.get("annotation_source"), str) or not entry["annotation_source"].strip() or not isinstance(entry.get("evidence_ref"), str) or not entry["evidence_ref"].strip():
                    raise DatasetPreparationError("Non-null source labels require annotation_source and evidence_ref")
            if any(entry.get(field) is not None for field in ("minimum_lumen_diameter", "reference_diameter", "percentage_narrowing")) and (not isinstance(entry.get("measurement_units"), str) or not entry["measurement_units"].strip() or not isinstance(entry.get("measurement_method"), str) or not entry["measurement_method"].strip()):
                raise DatasetPreparationError("Source measurements require explicit units and method")
    return {"schema_version": expected_schema, "entry_count": len(entries),
            "coordinate_space": coordinate_space, "geometry_fingerprint": image_geometry.fingerprint}


def _asset_paths(root: Path, raw: Any) -> list[tuple[str, Path, dict[str, Any]]]:
    if not isinstance(raw, list) or not raw:
        raise DatasetPreparationError("Each case must declare at least one asset")
    seen = set()
    result = []
    for item in raw:
        if not isinstance(item, dict) or set(item) - {"kind", "path", "format", "coordinate_space", "coordinate_frame", "spatial_units", "geometry_fingerprint", "label_schema"} or not {"kind", "path"}.issubset(item):
            raise DatasetPreparationError("Asset registration fields are invalid")
        kind = item.get("kind")
        if kind not in ASSET_KINDS:
            raise DatasetPreparationError("Unsupported asset kind")
        path = _safe_asset_path(root, item.get("path"))
        if item["path"] in seen:
            raise DatasetPreparationError("Duplicate asset path in case registration")
        seen.add(item["path"])
        result.append((kind, path, item))
    return result


def _case_record(root: Path, case: Any) -> dict[str, Any]:
    if not isinstance(case, dict) or set(case) - {"case_id", "patient_group_id", "split", "assets"}:
        raise DatasetPreparationError("Case registration has unsupported fields")
    case_id = _safe_id(case.get("case_id"), "case ID")
    group_id = _safe_id(case.get("patient_group_id"), "patient group ID")
    split = case.get("split", "unassigned")
    if split not in SPLITS:
        raise DatasetPreparationError("Case split must be train, validation, test, or unassigned")
    declared = _asset_paths(root, case.get("assets"))
    images = [(p, meta) for kind, p, meta in declared if kind == "image"]
    if len(images) != 1:
        raise DatasetPreparationError("Each case must declare exactly one source image or DICOM series")
    image_path, image_meta = images[0]
    geometry, image_identity = inspect_image(image_path, image_meta.get("format"))
    assets = []
    for kind, path, meta in declared:
        if kind == "image":
            assets.append({"kind": kind, "path": meta["path"], "identity": image_identity, "geometry": geometry.as_dict(), "geometry_fingerprint": geometry.fingerprint, "alignment": "source"})
        elif kind == "vessel_mask":
            candidate, identity = inspect_image(path, meta.get("format"))
            alignment = _compare_geometry(geometry, candidate, "Vessel mask")
            observed = _scan_label_values(path, meta.get("format", ""), candidate)
            label_schema = _validate_label_schema(meta.get("label_schema"), observed)
            assets.append({"kind": kind, "path": meta["path"], "identity": identity, "geometry": candidate.as_dict(), "geometry_fingerprint": candidate.fingerprint, "label_schema": label_schema, "alignment": alignment, "label_values_status": "verified_against_declared_schema"})
        elif kind in {"centerline", "lesion_annotation"}:
            summary = _validate_structured_annotation(path, kind, geometry)
            assets.append({"kind": kind, "path": meta["path"], "identity": {"sha256": _file_sha256(path), "size_bytes": path.stat().st_size}, "annotation_summary": summary, "alignment": "verified_source_geometry_and_bounds"})
        else:
            if not path.is_file():
                raise DatasetPreparationError("Spatial annotation assets must be files")
            if kind == "mesh":
                spatial_summary = _validate_mesh(path, geometry, meta)
                alignment = "verified_vertex_bounds_and_geometry_binding"
            else:
                fingerprint, frame, units = meta.get("geometry_fingerprint"), meta.get("coordinate_frame"), meta.get("spatial_units")
                if fingerprint != geometry.fingerprint or not frame or not units:
                    raise DatasetPreparationError("External annotation requires matching geometry fingerprint, coordinate frame, and units")
                spatial_summary = {"geometry_fingerprint": fingerprint, "coordinate_frame": frame, "spatial_units": units}
                alignment = "declared_external_annotation_geometry_binding"
            assets.append({"kind": kind, "path": meta["path"], "identity": {"sha256": _file_sha256(path), "size_bytes": path.stat().st_size}, "spatial_summary": spatial_summary, "alignment": alignment})
    return {"case_id": case_id, "patient_group_id": group_id, "split": split,
            "geometry": geometry.as_dict(),
            "geometry_fingerprint": geometry.fingerprint, "assets": assets}


def validate_patient_splits(cases: Iterable[dict[str, Any]]) -> None:
    group_splits: dict[str, set[str]] = {}
    for case in cases:
        group_splits.setdefault(case["patient_group_id"], set()).add(case["split"])
    if any(len(values) > 1 for values in group_splits.values()):
        raise DatasetPreparationError("Patient-level leakage: one patient group appears in multiple split states")


def assign_patient_splits(cases: list[dict[str, Any]], ratios: dict[str, float], seed: int) -> list[dict[str, Any]]:
    """Deterministically assign whole patient groups; does not stratify by labels."""
    if set(ratios) != {"train", "validation", "test"} or any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in ratios.values()) or not math.isclose(sum(ratios.values()), 1.0, abs_tol=1e-9):
        raise DatasetPreparationError("Split ratios must be positive and sum to one")
    if type(seed) is not int:
        raise DatasetPreparationError("Split seed must be an integer")
    groups = sorted({_safe_id(c.get("patient_group_id"), "patient group ID") for c in cases})
    ordered = sorted(groups, key=lambda group: hashlib.sha256(f"{seed}:{group}".encode()).digest())
    cumulative = np.cumsum([ratios["train"], ratios["validation"]]).tolist()
    result = []
    mapping = {}
    for index, group in enumerate(ordered):
        point = (index + 0.5) / max(1, len(ordered))
        mapping[group] = "train" if point < cumulative[0] else "validation" if point < cumulative[1] else "test"
    for case in cases:
        updated = dict(case)
        updated["split"] = mapping[case["patient_group_id"]]
        result.append(updated)
    validate_patient_splits(result)
    return result


def prepare_dataset(root: str | Path, registration: dict[str, Any]) -> dict[str, Any]:
    """Validate source assets and return a deterministic, content-bound manifest."""
    dataset_root = Path(root).resolve(strict=True)
    if not dataset_root.is_dir():
        raise DatasetPreparationError("Dataset root must be a directory")
    allowed = {"schema_version", "dataset", "preprocessing", "cases"}
    if not isinstance(registration, dict) or set(registration) != allowed or registration.get("schema_version") != "vascuai-dataset-registration/0.1":
        raise DatasetPreparationError("Registration document is not the supported versioned schema")
    dataset = registration.get("dataset")
    required_dataset = {"family", "name", "version", "source", "modality", "license", "access_status", "deidentification_status", "evidence_refs"}
    if not isinstance(dataset, dict) or set(dataset) != required_dataset:
        raise DatasetPreparationError("Dataset source, version, access, license, and de-identification evidence are required")
    if dataset["family"] not in DATASET_FAMILIES:
        raise DatasetPreparationError("Unsupported dataset family")
    if dataset["access_status"] not in {"open", "restricted", "unknown"} or dataset["deidentification_status"] != "dataset_documented_deidentified":
        raise DatasetPreparationError("Dataset access and documented de-identification must be established before registration")
    license_info = dataset["license"]
    if not isinstance(license_info, dict) or set(license_info) != {"name", "status", "evidence_ref"} or license_info["status"] not in {"confirmed", "unconfirmed", "restricted"}:
        raise DatasetPreparationError("License status and evidence reference are required")
    for field in ("name", "version", "source"):
        if not isinstance(dataset[field], str) or not dataset[field].strip() or len(dataset[field]) > 2048:
            raise DatasetPreparationError(f"Dataset {field} is required and must be bounded text")
    if dataset["modality"] != "CCTA":
        raise DatasetPreparationError("This module registers coronary CT angiography datasets only")
    if not isinstance(dataset["evidence_refs"], list) or not dataset["evidence_refs"] or any(not isinstance(ref, str) or not ref.strip() or len(ref) > 2048 or Path(ref).is_absolute() or "\\" in ref for ref in dataset["evidence_refs"]):
        raise DatasetPreparationError("Dataset documentation/manifests must be referenced")
    if not isinstance(license_info["name"], str) or not license_info["name"].strip() or not isinstance(license_info["evidence_ref"], str) or not license_info["evidence_ref"].strip() or Path(license_info["evidence_ref"]).is_absolute() or "\\" in license_info["evidence_ref"]:
        raise DatasetPreparationError("License name and evidence reference are required")
    preprocessing = _validate_preprocessing(registration["preprocessing"])
    raw_cases = registration.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise DatasetPreparationError("Registration must contain at least one case")
    prepared = [_case_record(dataset_root, case) for case in raw_cases]
    ids = [case["case_id"] for case in prepared]
    if len(set(ids)) != len(ids):
        raise DatasetPreparationError("Duplicate de-identified case IDs")
    validate_patient_splits(prepared)
    manifest = {
        "schema_version": MANIFEST_SCHEMA,
        "dataset": json.loads(canonical_json(dataset)),
        "preprocessing": {**preprocessing, "sha256": canonical_sha256(preprocessing)},
        "cases": sorted(prepared, key=lambda c: c["case_id"]),
        "statistics": summarize_cases(prepared),
        "eligibility": {
            # Restricted datasets need a separate recorded authorization; this
            # generic registration tool cannot grant access or use rights.
            "training_eligible": False,
            "license_access_precheck_passed": bool(license_info["status"] == "confirmed" and dataset["access_status"] == "open"),
            "lesion_annotation_assets_present": any(a["kind"] == "lesion_annotation" for c in prepared for a in c["assets"]),
            "training_eligibility": "not_evaluated_by_preparation_tool",
            "dataset_membership_and_label_semantics_independently_reviewed": False,
        },
        "registration": json.loads(canonical_json(registration)),
    }
    manifest["manifest_sha256"] = canonical_sha256(manifest)
    return manifest


def verify_manifest(root: str | Path, manifest: dict[str, Any]) -> dict[str, Any]:
    """Verify manifest self-hash and re-inventory the original source assets."""
    if not isinstance(manifest, dict) or manifest.get("schema_version") != MANIFEST_SCHEMA:
        raise DatasetPreparationError("Unsupported dataset manifest version")
    expected = manifest.get("manifest_sha256")
    body = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    if not isinstance(expected, str) or canonical_sha256(body) != expected:
        raise DatasetPreparationError("Dataset manifest integrity check failed")
    registration = manifest.get("registration")
    if not isinstance(registration, dict):
        raise DatasetPreparationError("Manifest lacks source registration needed for verification")
    rebuilt = prepare_dataset(root, registration)
    if rebuilt["manifest_sha256"] != expected:
        raise DatasetPreparationError("Dataset assets or registration differ from the recorded manifest")
    return {"verified": True, "manifest_sha256": expected, "case_count": len(manifest["cases"])}


def summarize_cases(cases: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {kind: 0 for kind in sorted(ASSET_KINDS)}
    missing: dict[str, int] = {kind: 0 for kind in ("vessel_mask", "centerline", "mesh", "lesion_annotation")}
    split_counts: dict[str, int] = {split: 0 for split in sorted(SPLITS)}
    geometry_fingerprints = set()
    annotation_entries = {"centerline": 0, "lesion_annotation": 0}
    for case in cases:
        split_counts[case["split"]] += 1
        kinds = {asset["kind"] for asset in case["assets"]}
        geometry_fingerprints.add(case["geometry_fingerprint"])
        for kind in kinds:
            counts[kind] += 1
        for kind in missing:
            if kind not in kinds:
                missing[kind] += 1
        for asset in case["assets"]:
            if asset["kind"] in annotation_entries:
                annotation_entries[asset["kind"]] += asset.get("annotation_summary", {}).get("entry_count", 0)
    return {"case_count": len(cases), "unique_patient_group_count": len({c["patient_group_id"] for c in cases}),
            "case_counts_by_split": split_counts, "asset_case_counts": counts, "cases_missing_asset": missing,
            "annotation_entry_counts": annotation_entries,
            "unique_geometry_count": len(geometry_fingerprints)}


def write_manifest(path: str | Path, manifest: dict[str, Any]) -> None:
    """Exclusive, atomic manifest creation; never overwrite existing output."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_json(manifest) + b"\n"
    temp = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    try:
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temp, target)  # hard-link creation fails if target already exists
    except FileExistsError as exc:
        raise DatasetPreparationError("Manifest output already exists; choose a new path") from exc
    except OSError as exc:
        raise DatasetPreparationError("Manifest could not be created exclusively") from exc
    finally:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass
