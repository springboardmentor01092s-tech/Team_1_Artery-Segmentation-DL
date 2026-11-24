"""Pure/synthetic gate tests. Run with --noconftest: no migrations or real DB."""
from copy import deepcopy
from types import SimpleNamespace
from types import MappingProxyType
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.core.quantitative_gate import (
    GATE_UNAVAILABLE_REASON, QuantitativeGateError, VALIDATED_GATES,
    require_measurement_gate, require_reportable_result,
)
from app.schemas.stenosis import AnalysisResult, Measurement


def numeric(value=0, unit="mm"):
    return dict(value=value, unit=unit, unavailable_reason=None, method_id="synthetic-test-only",
                method_version="v1", definition="Synthetic bypass attempt, not a validated measurement")


def claimed_gate():
    # Deliberately unregistered negative fixture; never added to either registry.
    return dict(gate_id="synthetic-unregistered", gate_version="v1", evidence_sha256="a" * 64,
                analysis_method_id="synthetic-test-only", analysis_method_version="v1",
                source_sha256="b" * 64, checkpoint_sha256=None)


def result_with(measurement, name="reference_diameter"):
    missing = dict(value=None, unit="mm", unavailable_reason={"code": "not_integrated", "message": GATE_UNAVAILABLE_REASON})
    measurements = {field: deepcopy(missing) for field in ("reference_diameter", "minimum_lumen_diameter", "percentage_narrowing")}
    measurements["percentage_narrowing"]["unit"] = "percent"
    measurements[name] = measurement
    reason = {"code": "not_integrated", "message": "Synthetic fixture: no validated measurement method"}
    return {"contract_version": "1.0", "analysis_id": uuid4(), "state": "completed", "unavailable_reason": None,
            "provenance": {"contract_version": "1.0", "method_id": "synthetic-test-only", "method_version": "v1",
                           "created_at": datetime.now(timezone.utc), "checkpoint_sha256": None,
                           "source": {"case_id": 1, "image_reference": "case-volume", "source_sha256": "b" * 64,
                                      "parent_segmentation_result_id": uuid4()},
                           "geometry": {"shape": [2, 2, 2], "array_axis_order": "nifti_i_j_k", "world_convention": "RAS",
                                        "world_unit": "mm", "affine": [[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]]}},
            "lesions": [{"lesion_id": uuid4(), "measurements": measurements, "location": None,
                         "localization_unavailable_reason": reason,
                         "severity": {"category": None, "unavailable_reason": reason},
                         "explanation": {"artifact_id": None, "unavailable_reason": reason}}]}


def test_no_registered_gate_or_runtime_activation():
    from app.services.stenosis_runtime import get_runtime
    from app.services.stenosis import capabilities
    assert not VALIDATED_GATES
    with pytest.raises(TypeError):
        VALIDATED_GATES["synthetic-unregistered"] = object()
    assert get_runtime() is None
    assert all(not item.execution_permitted for item in capabilities().capabilities)


@pytest.mark.parametrize("value", [0, 1, 50, 100])
@pytest.mark.parametrize("unit", ["mm", "percent"])
def test_zero_and_other_supplied_numbers_require_real_gate(value, unit):
    with pytest.raises(ValidationError, match="validated quantitative"):
        Measurement(**numeric(value, unit))


@pytest.mark.parametrize("change", ["matching_claim", "method", "version", "source", "checkpoint", "evidence", "flag", "malformed_id"])
def test_claims_and_mismatches_never_self_validate(change):
    value = numeric(25, "percent")
    gate = claimed_gate()
    if change == "method": gate["analysis_method_id"] = "different"
    if change == "version": gate["analysis_method_version"] = "different"
    if change == "source": gate["source_sha256"] = "c" * 64
    if change == "checkpoint": gate["checkpoint_sha256"] = "d" * 64
    if change == "evidence": gate["evidence_sha256"] = "e" * 64
    if change == "flag": gate["validated"] = True
    if change == "malformed_id": gate["gate_id"] = []
    value["validation_gate"] = gate
    with pytest.raises(QuantitativeGateError):
        require_reportable_result(result_with(value))
    with pytest.raises(ValidationError):
        Measurement(**value)


def test_unavailable_retains_reason_and_optional_method_provenance():
    value = Measurement(value=None, unit="mm", unavailable_reason={"code": "not_integrated", "message": GATE_UNAVAILABLE_REASON},
                        method_id="synthetic-test-only")
    assert value.value is None and value.method_id == "synthetic-test-only"
    assert value.unavailable_reason.message == GATE_UNAVAILABLE_REASON
    require_measurement_gate(value)
    # Segmentation evaluation zero scores are a different schema and remain valid.
    from app.schemas.evaluation import Metrics
    assert Metrics(dice=0, iou=0, precision=0, recall=0).dice == 0


@pytest.mark.parametrize("name", ["reference_diameter", "minimum_lumen_diameter", "percentage_narrowing"])
def test_model_construct_or_mutation_does_not_bypass_result_policy(name):
    data = result_with(Measurement.model_construct(**numeric()), name)
    constructed = AnalysisResult.model_construct(**data)
    with pytest.raises(QuantitativeGateError):
        require_reportable_result(constructed)
    with pytest.raises(ValidationError, match="validated quantitative"):
        AnalysisResult.model_validate(constructed)


@pytest.mark.parametrize("name", ["reference_diameter", "minimum_lumen_diameter", "percentage_narrowing"])
def test_writer_rejects_before_any_database_or_storage_operation(name, monkeypatch):
    from app.services import stenosis_results as results
    calls = []
    def forbidden(*args, **kwargs):
        calls.append("side effect")
        raise AssertionError("Gate rejection must precede persistence/source IO")
    monkeypatch.setattr(results.jobs, "require_runtime", forbidden)
    monkeypatch.setattr(results, "source_geometry", forbidden)
    monkeypatch.setattr(results, "copy_regions", forbidden)
    class NoDatabase:
        def __getattr__(self, key):
            return forbidden
    with pytest.raises(HTTPException) as failure:
        results.persist_completed_result(NoDatabase(), None, None, result_with(numeric(), name), None)
    assert failure.value.detail["code"] == "quantitative_gate_unavailable"
    assert not calls


def test_legacy_numeric_result_reader_withholds_before_typed_response():
    from app.services.stenosis_results import SQLResultStore
    payload = result_with(numeric())
    # Read-only in-memory query doubles; no database or records are created.
    row = SimpleNamespace(id="synthetic-read-only", provenance_json=payload["provenance"])
    lesion = SimpleNamespace(payload_json=payload["lesions"][0])
    db = SimpleNamespace(scalar=lambda query: row, scalars=lambda query: SimpleNamespace(all=lambda: [lesion]))
    with pytest.raises(HTTPException) as failure:
        SQLResultStore().load(db, "synthetic-read-only")
    assert failure.value.detail["code"] == "quantitative_gate_unavailable"
    assert lesion.payload_json["measurements"]["reference_diameter"]["value"] == 0  # never rewrite stored evidence


def test_csv_cannot_export_constructed_or_mutated_non_gate_backed_result():
    from app.services.stenosis_reporting import csv_report
    value = SimpleNamespace(report_state="completed", result=SimpleNamespace(result=result_with(numeric(25, "percent"))))
    with pytest.raises(HTTPException) as failure:
        csv_report(value)
    assert failure.value.detail["code"] == "quantitative_gate_unavailable"


def test_readonly_mapping_cannot_bypass_early_policy():
    with pytest.raises(QuantitativeGateError):
        require_reportable_result(MappingProxyType(result_with(numeric())))


def test_analytics_never_counts_unvalidated_legacy_numbers_as_available():
    from app.services.stenosis_analytics import reportable_measurement_count
    class NoDatabase:
        def __getattr__(self, name):
            raise AssertionError("An empty gate registry must not query numeric payloads")
    for field in ("reference_diameter", "minimum_lumen_diameter", "percentage_narrowing"):
        assert reportable_measurement_count(NoDatabase(), ["synthetic-read-only"], field) == 0


def test_research_report_preserves_explicit_gate_failure(monkeypatch):
    from app.services import stenosis_reporting as reporting
    monkeypatch.setattr(reporting.jobs, "get_job", lambda *args: SimpleNamespace(stale=False, status="completed"))
    def blocked(*args):
        raise HTTPException(409, {"code": "quantitative_gate_unavailable", "message": GATE_UNAVAILABLE_REASON})
    monkeypatch.setattr(reporting.results, "retrieve_result", blocked)
    db = SimpleNamespace(get=lambda *args: SimpleNamespace(id=1, case_code="synthetic-test-only", patient_id=1))
    with pytest.raises(HTTPException) as failure:
        reporting.report(db, 1, "synthetic-test-only")
    assert failure.value.detail["code"] == "quantitative_gate_unavailable"
    assert failure.value.detail["message"] == GATE_UNAVAILABLE_REASON
