from __future__ import annotations

import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import nibabel as nib
import numpy as np
import pytest

from app.services.ccta_dataset_preparation import (
    DatasetPreparationError,
    assign_patient_splits,
    inspect_image,
    prepare_dataset,
    verify_manifest,
    write_manifest,
)


def _write_nifti(path: Path, data: np.ndarray, affine=None) -> None:
    image = nib.Nifti1Image(data, np.eye(4) if affine is None else affine)
    image.header.set_xyzt_units("mm")
    nib.save(image, path)


def _registration(image="ct.nii.gz", mask="mask.nii.gz", family="imagecas_x"):
    return {
        "schema_version": "vascuai-dataset-registration/0.1",
        "dataset": {
            "family": family, "name": "synthetic QA only", "version": "fixture-1",
            "source": "https://example.invalid/synthetic-fixture", "modality": "CCTA",
            "license": {"name": "Unconfirmed fixture terms", "status": "unconfirmed", "evidence_ref": "fixture-license-note"},
            "access_status": "open", "deidentification_status": "dataset_documented_deidentified",
            "evidence_refs": ["synthetic-fixture-documentation"],
        },
        "preprocessing": {
            "schema_version": "vascuai-ccta-preprocessing/0.1", "orientation_policy": "preserve_native",
            "target_spacing": None, "target_spacing_units": None, "resampling": "none", "image_interpolation": None,
            "mask_interpolation": None, "intensity_transform": {"kind": "none"},
            "crop_policy": "none", "software_versions": {"qa": "synthetic"}, "seed": 42,
        },
        "cases": [{
            "case_id": "case-001", "patient_group_id": "subject-001", "split": "train",
            "assets": [
                {"kind": "image", "path": image, "format": "nifti"},
                {"kind": "vessel_mask", "path": mask, "format": "nifti",
                 "label_schema": {"schema_version": "vascuai-label-map/0.1", "labels": [
                     {"value": 0, "meaning": "background"}, {"value": 1, "meaning": "artery"}]}}
            ],
        }],
    }


@pytest.fixture
def dataset_root(tmp_path):
    root = tmp_path / "dataset"
    root.mkdir()
    ct = np.arange(8 * 9 * 10, dtype=np.int16).reshape(8, 9, 10)
    mask = np.zeros((8, 9, 10), dtype=np.uint8)
    mask[2:5, 3:7, 3:8] = 1
    affine = np.array([[0, -0.7, 0, 12], [1.1, 0, 0, -8], [0, 0, 1.8, 3], [0, 0, 0, 1]], dtype=float)
    _write_nifti(root / "ct.nii.gz", ct, affine)
    _write_nifti(root / "mask.nii.gz", mask, affine)
    return root


def test_prepare_manifest_preserves_native_geometry_and_hashes(dataset_root):
    registration = _registration()
    ct_before = (dataset_root / "ct.nii.gz").read_bytes()
    mask_before = (dataset_root / "mask.nii.gz").read_bytes()
    manifest = prepare_dataset(dataset_root, registration)
    case = manifest["cases"][0]
    assert case["geometry"]["dimensions"] == [8, 9, 10]
    assert case["geometry"]["coordinate_frame"] == "RAS"
    assert case["geometry"]["voxel_spacing"] == pytest.approx([1.1, 0.7, 1.8])
    assert case["assets"][1]["label_schema"]["observed_values"] == [0, 1]
    assert manifest["eligibility"]["training_eligible"] is False
    assert manifest["eligibility"]["dataset_membership_and_label_semantics_independently_reviewed"] is False
    assert (dataset_root / "ct.nii.gz").read_bytes() == ct_before
    assert (dataset_root / "mask.nii.gz").read_bytes() == mask_before
    assert verify_manifest(dataset_root, manifest)["verified"] is True


def test_manifest_rejects_mask_geometry_mismatch(dataset_root):
    _write_nifti(dataset_root / "bad-mask.nii.gz", np.zeros((8, 9, 10), dtype=np.uint8), np.diag([1, 1, 1, 1]))
    reg = _registration(mask="bad-mask.nii.gz")
    with pytest.raises(DatasetPreparationError, match="affine"):
        prepare_dataset(dataset_root, reg)


def test_mask_with_unknown_units_is_registered_without_claiming_physical_unit_alignment(dataset_root):
    mask_path = dataset_root / "mask.nii.gz"
    image = nib.load(str(mask_path))
    image.header.set_xyzt_units("unknown")
    nib.save(image, mask_path)
    result = prepare_dataset(dataset_root, _registration())
    mask = result["cases"][0]["assets"][1]
    assert mask["alignment"] == "shape_affine_frame_verified_units_unresolved"
    assert mask["geometry"]["spatial_units"] == "unknown"


def test_mask_with_conflicting_known_units_is_rejected(dataset_root):
    affine = np.diag([0.001, 0.001, 0.001, 1.0])
    _write_nifti(dataset_root / "ct.nii.gz", np.zeros((8, 9, 10), dtype=np.int16), affine)
    mask_path = dataset_root / "mask.nii.gz"
    image = nib.Nifti1Image(np.zeros((8, 9, 10), dtype=np.uint8), affine)
    image.header.set_xyzt_units("meter")
    nib.save(image, mask_path)
    with pytest.raises(DatasetPreparationError, match="coordinate units"):
        prepare_dataset(dataset_root, _registration())


def test_manifest_rejects_observed_label_not_declared(dataset_root):
    reg = _registration()
    reg["cases"][0]["assets"][1]["label_schema"]["labels"] = [{"value": 0, "meaning": "background"}]
    with pytest.raises(DatasetPreparationError, match="Observed vessel mask labels"):
        prepare_dataset(dataset_root, reg)


def test_manifest_requires_documented_label_schema(dataset_root):
    reg = _registration()
    reg["cases"][0]["assets"][1].pop("label_schema")
    with pytest.raises(DatasetPreparationError, match="versioned label schema"):
        prepare_dataset(dataset_root, reg)


def test_patient_split_assignment_is_deterministic_and_grouped():
    cases = [{"case_id": f"c{i}", "patient_group_id": f"p{i // 2}", "split": "unassigned"} for i in range(20)]
    a = assign_patient_splits(cases, {"train": .6, "validation": .2, "test": .2}, 19)
    b = assign_patient_splits(cases, {"train": .6, "validation": .2, "test": .2}, 19)
    assert a == b
    for patient in {row["patient_group_id"] for row in a}:
        assert len({row["split"] for row in a if row["patient_group_id"] == patient}) == 1


def test_patient_split_leakage_is_rejected(dataset_root):
    reg = _registration()
    case2 = dict(reg["cases"][0], case_id="case-002", split="validation")
    reg["cases"].append(case2)
    with pytest.raises(DatasetPreparationError, match="Patient-level leakage"):
        prepare_dataset(dataset_root, reg)


def test_path_traversal_and_symlink_are_rejected(dataset_root, tmp_path):
    reg = _registration(image="../outside.nii.gz")
    with pytest.raises(DatasetPreparationError, match="traversal"):
        prepare_dataset(dataset_root, reg)
    link = dataset_root / "linked.nii.gz"
    try:
        link.symlink_to(dataset_root / "ct.nii.gz")
    except OSError:
        pytest.skip("Host does not permit symlink creation")
    reg = _registration(image="linked.nii.gz")
    with pytest.raises(DatasetPreparationError, match="Symlink"):
        prepare_dataset(dataset_root, reg)


def test_structured_lesion_annotations_bind_geometry_and_preserve_nulls(dataset_root):
    geometry, _ = inspect_image(dataset_root / "ct.nii.gz")
    annotation = {
        "schema_version": "vascuai-lesion-annotation/0.1",
        "geometry_fingerprint": geometry.fingerprint,
        "coordinate_space": "native_ijk",
        "protocol_ref": "synthetic-test-protocol",
        "lesions": [{"id": "lesion-1", "center_ijk": [3, 4, 5],
                     "proximal_boundary_ijk": [3, 4, 4], "distal_boundary_ijk": [3, 4, 6],
                     "minimum_lumen_diameter": None, "reference_diameter": None,
                     "percentage_narrowing": None, "severity_category": None}],
    }
    (dataset_root / "lesions.json").write_text(json.dumps(annotation), encoding="utf-8")
    reg = _registration()
    reg["cases"][0]["assets"].append({"kind": "lesion_annotation", "path": "lesions.json"})
    prepared = prepare_dataset(dataset_root, reg)
    assert prepared["eligibility"]["lesion_annotation_assets_present"] is True
    assert prepared["eligibility"]["training_eligible"] is False


def test_structured_annotation_rejects_outside_coordinate_and_wrong_fingerprint(dataset_root):
    geometry, _ = inspect_image(dataset_root / "ct.nii.gz")
    doc = {"schema_version": "vascuai-centerline/0.1", "geometry_fingerprint": geometry.fingerprint,
           "coordinate_space": "native_ijk", "points": [{"id": "p1", "ijk": [99, 0, 0]}]}
    (dataset_root / "centerline.json").write_text(json.dumps(doc), encoding="utf-8")
    reg = _registration()
    reg["cases"][0]["assets"].append({"kind": "centerline", "path": "centerline.json"})
    with pytest.raises(DatasetPreparationError, match="outside"):
        prepare_dataset(dataset_root, reg)
    doc["geometry_fingerprint"] = "0" * 64
    (dataset_root / "centerline.json").write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(DatasetPreparationError, match="fingerprint"):
        prepare_dataset(dataset_root, reg)


def test_obj_mesh_vertices_are_checked_in_native_ijk(dataset_root):
    geometry, _ = inspect_image(dataset_root / "ct.nii.gz")
    mesh = dataset_root / "surface.obj"
    mesh.write_text("v 1 2 3\nv 6 7 8\nf 1 2 1\n", encoding="utf-8")
    reg = _registration()
    reg["cases"][0]["assets"].append({"kind": "mesh", "path": "surface.obj", "coordinate_space": "native_ijk",
                                          "geometry_fingerprint": geometry.fingerprint})
    prepared = prepare_dataset(dataset_root, reg)
    assert prepared["cases"][0]["assets"][-1]["spatial_summary"]["vertex_count"] == 2
    mesh.write_text("v 100 2 3\n", encoding="utf-8")
    with pytest.raises(DatasetPreparationError, match="outside"):
        prepare_dataset(dataset_root, reg)


def test_manifest_verification_detects_changed_source_and_collision(dataset_root, tmp_path):
    manifest = prepare_dataset(dataset_root, _registration())
    output = tmp_path / "manifest.json"
    write_manifest(output, manifest)
    with pytest.raises(DatasetPreparationError, match="already exists"):
        write_manifest(output, manifest)
    (dataset_root / "ct.nii.gz").write_bytes(b"changed")
    with pytest.raises(DatasetPreparationError):
        verify_manifest(dataset_root, manifest)


def test_dicom_series_header_geometry_adapter_without_pixel_decode(tmp_path, monkeypatch):
    directory = tmp_path / "dicom"
    directory.mkdir()
    for name in ("a.dcm", "b.dcm"):
        (directory / name).write_bytes(name.encode())
    def dcmread(path, **kwargs):
        z = 0.0 if Path(path).name == "a.dcm" else 1.5
        return SimpleNamespace(SeriesInstanceUID="series", SOPInstanceUID=Path(path).name,
            Rows=3, Columns=4, ImagePositionPatient=[10, 20, z],
            ImageOrientationPatient=[1, 0, 0, 0, 1, 0], PixelSpacing=[0.6, 0.8],
            Modality="CT", BitsAllocated=16, BitsStored=12, PixelRepresentation=1,
            RescaleSlope=1.0, RescaleIntercept=-1024.0, PhotometricInterpretation="MONOCHROME2")
    monkeypatch.setitem(sys.modules, "pydicom", SimpleNamespace(dcmread=dcmread))
    geometry, identity = inspect_image(directory, "dicom")
    assert geometry.dimensions == (4, 3, 2)
    assert geometry.spacing == pytest.approx((0.8, 0.6, 1.5))
    assert geometry.coordinate_frame == "LPS"
    assert identity["instance_count"] == 2
    assert "series_instance_uid" not in identity


def test_nrrd_header_geometry_adapter_and_missing_dependency_behavior(tmp_path, monkeypatch):
    path = tmp_path / "sample.nrrd"
    path.write_bytes(b"synthetic header fixture")
    module = ModuleType("nrrd")
    module.read_header = lambda *_a, **_k: {"sizes": [4, 3, 2], "space directions": [[.7, 0, 0], [0, 1.1, 0], [0, 0, 2]], "space origin": [5, 6, 7], "space": "right-anterior-superior", "space units": ["mm", "mm", "mm"]}
    monkeypatch.setitem(sys.modules, "nrrd", module)
    geometry, _ = inspect_image(path, "nrrd")
    assert geometry.dimensions == (4, 3, 2)
    assert geometry.spacing == pytest.approx((.7, 1.1, 2))
    assert geometry.coordinate_frame == "RAS"
    monkeypatch.delitem(sys.modules, "nrrd")
    with pytest.raises(DatasetPreparationError, match="optional pynrrd"):
        inspect_image(path, "nrrd")


def test_nrrd_mask_alignment_and_label_values_are_validated(tmp_path, monkeypatch):
    root = tmp_path / "nrrd-set"
    root.mkdir()
    for name in ("ct.nrrd", "mask.nrrd"):
        (root / name).write_bytes(name.encode())
    header = {"sizes": [4, 3, 2], "space directions": [[.7, 0, 0], [0, 1.1, 0], [0, 0, 2]],
              "space origin": [5, 6, 7], "space": "right-anterior-superior", "space units": ["mm", "mm", "mm"],
              "type": "uint8"}
    labels = np.zeros((4, 3, 2), dtype=np.uint8); labels[1:3, 1, :] = 1
    module = ModuleType("nrrd")
    module.read_header = lambda *_a, **_k: dict(header)
    module.read = lambda path, **_k: (np.zeros_like(labels) if str(path).endswith("ct.nrrd") else labels.copy(), dict(header))
    monkeypatch.setitem(sys.modules, "nrrd", module)
    reg = _registration(image="ct.nrrd", mask="mask.nrrd")
    reg["cases"][0]["assets"][0]["format"] = "nrrd"
    reg["cases"][0]["assets"][1]["format"] = "nrrd"
    result = prepare_dataset(root, reg)
    assert result["cases"][0]["assets"][1]["label_schema"]["observed_values"] == [0, 1]
    module.read = lambda path, **_k: (np.full_like(labels, 2) if str(path).endswith("mask.nrrd") else np.zeros_like(labels), dict(header))
    with pytest.raises(DatasetPreparationError, match="Observed vessel mask labels"):
        prepare_dataset(root, reg)


def test_annotation_with_source_values_requires_provenance(dataset_root):
    geometry, _ = inspect_image(dataset_root / "ct.nii.gz")
    annotation = {"schema_version": "vascuai-lesion-annotation/0.1", "geometry_fingerprint": geometry.fingerprint,
                  "coordinate_space": "native_ijk", "protocol_ref": "synthetic-test-protocol", "lesions": [{"id": "lesion-1", "center_ijk": [3, 4, 5],
                  "proximal_boundary_ijk": [3, 4, 4], "distal_boundary_ijk": [3, 4, 6],
                  "percentage_narrowing": 20.0}]}
    (dataset_root / "labels.json").write_text(json.dumps(annotation), encoding="utf-8")
    reg = _registration()
    reg["cases"][0]["assets"].append({"kind": "lesion_annotation", "path": "labels.json"})
    with pytest.raises(DatasetPreparationError, match="annotation_source and evidence_ref"):
        prepare_dataset(dataset_root, reg)
    annotation["lesions"][0].update(annotation_source="dataset-provided", evidence_ref="annotation-guide")
    annotation["lesions"][0].update(measurement_units="mm", measurement_method="source-reported")
    (dataset_root / "labels.json").write_text(json.dumps(annotation), encoding="utf-8")
    assert prepare_dataset(dataset_root, reg)["eligibility"]["training_eligible"] is False


def test_unsupported_disease_level_fields_are_rejected(dataset_root):
    geometry, _ = inspect_image(dataset_root / "ct.nii.gz")
    annotation = {"schema_version": "vascuai-lesion-annotation/0.1", "geometry_fingerprint": geometry.fingerprint,
                  "coordinate_space": "native_ijk", "protocol_ref": "protocol", "lesions": [{"id": "lesion-1",
                  "center_ijk": [3, 4, 5], "proximal_boundary_ijk": [3, 4, 4], "distal_boundary_ijk": [3, 4, 6],
                  "disease_diagnosis": "not-an-input"}]}
    (dataset_root / "bad-labels.json").write_text(json.dumps(annotation), encoding="utf-8")
    reg = _registration()
    reg["cases"][0]["assets"].append({"kind": "lesion_annotation", "path": "bad-labels.json"})
    with pytest.raises(DatasetPreparationError, match="unsupported or unreviewed"):
        prepare_dataset(dataset_root, reg)
