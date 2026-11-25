"""Authenticated synthetic-only research API tests; no DB or patient data."""
import hashlib
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from pydantic import ValidationError

from app.core.dependencies import get_current_user, get_db
from app.core.roles import Role
from app.routers import experimental_stenosis as routes
from app.schemas.experimental_stenosis import ExperimentalAnalysisResponse, ExperimentalSampleResponse
from app.services.synthetic_stenosis_ml import train_synthetic_model


class AuditSink:
    def add(self, value): self.value = value
    def commit(self): pass


def client_for(role=Role.DATA_SCIENTIST):
    app = FastAPI()
    app.include_router(routes.router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=9, role=role)
    app.dependency_overrides[get_db] = lambda: AuditSink()
    return TestClient(app)


def unauthenticated_client():
    app = FastAPI()
    app.include_router(routes.router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: AuditSink()
    return TestClient(app)


def test_public_response_models_reject_synthetic_ground_truth_nested():
    sample = {
        "schema_version": "synthetic-stenosis-sample/0.2", "sample_id": 1,
        "shape": [24, 24, 24], "middle_slice_k": 12,
        "middle_slice": [[0.0] * 24 for _ in range(24)],
        "provenance": {"source": "vascuai-synthetic-vessel-phantom", "volume_sha256": "a" * 64},
        "notice": "synthetic", "clinical_validation": False,
        "clinical_gate_authorized": False, "training_release_authorized": False,
    }
    with pytest.raises(ValidationError):
        ExperimentalSampleResponse.model_validate({**sample, "provenance": {
            **sample["provenance"], "synthetic_geometry_ground_truth": {"lesions": []},
        }})

    analysis = {
        "schema_version": "experimental-stenosis-analysis/0.3",
        "generated_at": "2026-11-25T00:00:00Z", "status": "completed_synthetic_research_only",
        "notice": "synthetic", "provenance": {
            "synthetic_sample_id": 1, "volume_sha256": "a" * 64,
            "patient_case_id": None, "dataset_case_id": None,
        },
        "geometry_analysis": {"candidates": []}, "model": {}, "explainability": {},
        "clinical_validation": False, "clinical_gate_authorized": False,
        "training_release_authorized": False,
    }
    with pytest.raises(ValidationError):
        ExperimentalAnalysisResponse.model_validate({**analysis, "geometry_analysis": {
            "synthetic_geometry_ground_truth": {"lesions": []},
        }})


def test_analyze_route_serializes_only_prediction_not_synthetic_target(monkeypatch):
    payload = {
        "schema_version": "experimental-stenosis-analysis/0.3",
        "generated_at": "2026-11-25T00:00:00Z", "status": "completed_synthetic_research_only",
        "notice": "synthetic only", "provenance": {
            "synthetic_sample_id": 3, "generator_id": "vascuai-synthetic-vessel-phantom",
            "generator_version": "0.1.0", "volume_sha256": "a" * 64,
            "dataset_case_id": None, "patient_case_id": None,
        },
        "geometry_analysis": {"candidate_count": 0, "candidates": [], "metrics": {}},
        "model": {"predicted_synthetic_class": "moderate"},
        "explainability": {"scope": "synthetic_generated_phantom_only"},
        "clinical_validation": False, "clinical_gate_authorized": False,
        "training_release_authorized": False,
    }
    monkeypatch.setattr(routes, "checkpoint", lambda: (object(), {
        "test_metrics": {"scope": "synthetic_test_split_only"},
    }, "b" * 64))
    monkeypatch.setattr(routes, "analyze_synthetic_phantom", lambda *args, **kwargs: payload)
    response = client_for(Role.RESEARCHER).post("/api/v1/experimental-stenosis/analyze", json={
        "sample_id": 3, "synthetic_class_id": 2, "seed": 71,
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["schema_version"] == "experimental-stenosis-analysis/0.3"
    assert body["model"]["predicted_synthetic_class"] == "moderate"
    assert "synthetic_class_label" not in body["provenance"]
    assert "synthetic_geometry_ground_truth" not in str(body)


def test_auth_role_boundary_synthetic_generation_and_strict_request():
    client = client_for(Role.DATA_SCIENTIST)
    response = client.post("/api/v1/experimental-stenosis/samples", json={"sample_id": 4, "synthetic_class_id": 2, "seed": 71})
    assert response.status_code == 200
    value = response.json()
    assert value["schema_version"] == "synthetic-stenosis-sample/0.2"
    assert "class_label" not in value and "synthetic_geometry_ground_truth" not in value
    assert value["shape"] == [24, 24, 24]
    assert len(value["middle_slice"]) == 24 and len(value["middle_slice"][0]) == 24
    assert value["provenance"]["source"] == "vascuai-synthetic-vessel-phantom"
    assert "synthetic_geometry_ground_truth" not in value["provenance"]
    assert "controlled_max_diameter_reduction_fraction" not in value["provenance"]
    assert value["clinical_gate_authorized"] is False and value["training_release_authorized"] is False
    assert client.post("/api/v1/experimental-stenosis/samples", json={"sample_id": -1, "synthetic_class_id": 2, "seed": 71}).status_code == 422
    assert client.post("/api/v1/experimental-stenosis/samples", json={"sample_id": 4, "synthetic_class_id": 2, "seed": 71, "case_id": 7}).status_code == 422

    clinician = client_for(Role.CLINICIAN)
    assert clinician.post("/api/v1/experimental-stenosis/samples", json={"sample_id": 4, "synthetic_class_id": 2, "seed": 71}).status_code == 403
    assert unauthenticated_client().post("/api/v1/experimental-stenosis/samples", json={"sample_id": 4, "synthetic_class_id": 2, "seed": 71}).status_code == 401


def test_checkpoint_unavailable_and_wrong_hash_fail_closed(monkeypatch, tmp_path):
    client = client_for()
    monkeypatch.setattr(routes.settings, "VASCULAI_SYNTHETIC_STENOSIS_CHECKPOINT", None)
    monkeypatch.setattr(routes.settings, "VASCULAI_SYNTHETIC_STENOSIS_CHECKPOINT_SHA256", None)
    response = client.get("/api/v1/experimental-stenosis/status")
    assert response.status_code == 200 and response.json()["available"] is False
    path = tmp_path / "not-a-checkpoint.pt"
    path.write_bytes(b"synthetic test only")
    monkeypatch.setattr(routes.settings, "VASCULAI_SYNTHETIC_STENOSIS_CHECKPOINT", str(path))
    monkeypatch.setattr(routes.settings, "VASCULAI_SYNTHETIC_STENOSIS_CHECKPOINT_SHA256", "0" * 64)
    response = client.post("/api/v1/experimental-stenosis/analyze", json={"sample_id": 1, "synthetic_class_id": 2, "seed": 9})
    assert response.status_code == 503
    assert str(path) not in response.text


def test_analysis_returns_only_synthetic_provenance_gradcam_and_unverified_measurements(monkeypatch, tmp_path):
    pytest.importorskip("torch", reason="optional synthetic research model runtime is not installed")
    artifact = tmp_path / "model-run"
    model_run = train_synthetic_model(artifact, sample_count=25, epochs=1, seed=321)
    checkpoint = artifact / "synthetic-stenosis-cnn3d.pt"
    digest = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    client = client_for(Role.RESEARCHER)
    monkeypatch.setattr(routes.settings, "VASCULAI_SYNTHETIC_STENOSIS_CHECKPOINT", str(checkpoint))
    monkeypatch.setattr(routes.settings, "VASCULAI_SYNTHETIC_STENOSIS_CHECKPOINT_SHA256", digest)
    status = client.get("/api/v1/experimental-stenosis/status")
    assert status.status_code == 200 and status.json()["available"] is True
    thresholds = [5.0, 25.0, 45.0, 65.0]
    response = client.post("/api/v1/experimental-stenosis/analyze", json={
        "sample_id": 50, "synthetic_class_id": 3, "seed": 51,
        "provisional_severity_thresholds_percent": thresholds,
    })
    assert response.status_code == 200, response.text[:200]
    value = response.json()
    assert value["schema_version"] == "experimental-stenosis-analysis/0.3"
    assert "synthetic_class_label" not in value["provenance"]
    assert "synthetic_geometry_ground_truth" not in value["provenance"]
    assert value["geometry_analysis"]["measurement_provenance"]["input_volume_sha256"] == value["provenance"]["volume_sha256"]
    assert value["geometry_analysis"]["measurement_provenance"]["provisional_severity_thresholds_percent"] == thresholds
    assert value["geometry_analysis"]["metrics"]["measurement_confidence"] is None
    assert value["geometry_analysis"]["metrics"]["measurement_uncertainty"] is None
    assert value["status"] == "completed_synthetic_research_only"
    assert value["provenance"]["patient_case_id"] is None and value["provenance"]["dataset_case_id"] is None
    assert value["model"]["checkpoint_sha256"] == digest
    assert value["model"]["score_semantics"] == "uncalibrated_softmax_probability_not_clinical_confidence"
    assert value["explainability"]["method"] == "3d-cnn-grad-cam"
    assert value["explainability"]["shape"] == [24, 24, 24]
    assert len(value["explainability"]["heatmap_values"]) == 24 ** 3
    assert value["clinical_gate_authorized"] is False and value["training_release_authorized"] is False
    invalid_thresholds = client.post("/api/v1/experimental-stenosis/analyze", json={
        "sample_id": 50, "synthetic_class_id": 3, "seed": 51,
        "provisional_severity_thresholds_percent": [10.0, 50.0, 30.0, 70.0],
    })
    assert invalid_thresholds.status_code == 422
    for candidate in value["geometry_analysis"]["candidates"]:
        assert candidate["location"]["coordinate_space"] == "synthetic_IJK_voxel_units"
        assert candidate["measurements"]["quality"] == "synthetic_geometry_only_unvalidated"
        assert candidate["measurements"]["measurement_confidence"] is None
        assert candidate["measurements"]["measurement_uncertainty"] is None
    assert model_run["summary"]["clinical_validation"] is False
