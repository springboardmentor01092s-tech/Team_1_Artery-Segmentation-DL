"""API authorization, upload validation and non-persistence for real-volume QC."""
from types import SimpleNamespace

import nibabel as nib
import numpy as np
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.dependencies import get_current_user, get_db
from app.core.roles import Role
from app.routers.real_volume_research import router


def _nifti(mask=False, affine=None, units="mm"):
    data = np.zeros((24, 24, 24), dtype=np.uint8 if mask else np.int16)
    if mask:
        data[5:19, 10:14, 10:14] = 1
    image = nib.Nifti1Image(data, affine if affine is not None else np.diag([0.6, 0.8, 1.1, 1]))
    image.header.set_xyzt_units(xyz=units)
    return image.to_bytes()


def _client(role=Role.RESEARCHER):
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=7, role=role)
    app.dependency_overrides[get_db] = lambda: SimpleNamespace(add=lambda _: None, commit=lambda: None)
    return TestClient(app)


def test_authenticated_upload_returns_nonpersistent_abstention():
    response = _client().post("/api/v1/experimental-stenosis/real-volume/analyze", files={
        "ct_volume": ("ct.nii", _nifti(), "application/octet-stream"),
        "vessel_mask": ("mask.nii", _nifti(mask=True), "application/octet-stream"),
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["schema_version"] == "real-volume-research/0.1"
    assert body["candidate_status"] == "unavailable_mask_semantics_unverified"
    assert body["candidates"] == []
    assert body["measurements"]["estimated_percentage_narrowing"] is None
    assert body["clinical_validation"] is False
    assert body["clinical_gate_authorized"] is False
    assert body["training_release_authorized"] is False
    assert body["provenance"]["persisted"] is False
    assert body["provenance"]["synthetic_model_used"] is False


def test_research_roles_allowed_clinician_denied_and_invalid_inputs_rejected():
    for role in (Role.ADMIN, Role.DATA_SCIENTIST, Role.RESEARCHER):
        response = _client(role).post("/api/v1/experimental-stenosis/real-volume/analyze", files={
            "ct_volume": ("ct.nii", _nifti(), "application/octet-stream"),
            "vessel_mask": ("mask.nii", _nifti(mask=True), "application/octet-stream"),
        })
        assert response.status_code == 200
    denied = _client(Role.CLINICIAN).post("/api/v1/experimental-stenosis/real-volume/analyze", files={
        "ct_volume": ("ct.nii", _nifti(), "application/octet-stream"),
        "vessel_mask": ("mask.nii", _nifti(mask=True), "application/octet-stream"),
    })
    assert denied.status_code == 403
    missing = _client().post("/api/v1/experimental-stenosis/real-volume/analyze", files={
        "ct_volume": ("ct.nii", _nifti(), "application/octet-stream"),
    })
    assert missing.status_code == 422
    wrong_type = _client().post("/api/v1/experimental-stenosis/real-volume/analyze", files={
        "ct_volume": ("ct.dcm", b"not dicom", "application/octet-stream"),
        "vessel_mask": ("mask.nii", _nifti(mask=True), "application/octet-stream"),
    })
    assert wrong_type.status_code == 422


def test_affine_mismatch_is_rejected():
    shifted = np.diag([0.6, 0.8, 1.1, 1]); shifted[0, 3] = 1
    response = _client().post("/api/v1/experimental-stenosis/real-volume/analyze", files={
        "ct_volume": ("ct.nii", _nifti(affine=np.diag([0.6, 0.8, 1.1, 1])), "application/octet-stream"),
        "vessel_mask": ("mask.nii", _nifti(mask=True, affine=shifted), "application/octet-stream"),
    })
    assert response.status_code == 422
    assert "affine_mismatch" in response.json()["detail"]
