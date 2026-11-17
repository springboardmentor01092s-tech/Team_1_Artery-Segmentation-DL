"""Reportability policy, independent of DB, runtime toggles and supplied claims.

No gate has passed validation. Registry entries may only be introduced by a
separately reviewed code/evidence change, never by a request or environment flag.
"""
from dataclasses import dataclass
from collections.abc import Mapping
from types import MappingProxyType

GATE_UNAVAILABLE_REASON = "No validated quantitative stenosis gate is registered; measurement unavailable."


class QuantitativeGateError(ValueError):
    pass


@dataclass(frozen=True)
class ValidatedGate:
    version: str
    evidence_sha256: str
    method_id: str
    method_version: str
    analysis_method_id: str
    analysis_method_version: str
    checkpoint_sha256: str | None
    unit: str
    definition: str | None
    reference_region: str | None


# Empty by design: accepting a supplied ID/hash/validated=True is not validation.
VALIDATED_GATES = MappingProxyType({})


def field(value, name, default=None):
    return value.get(name, default) if isinstance(value, Mapping) else getattr(value, name, default)


def require_measurement_gate(measurement, provenance=None):
    if field(measurement, "value") is None:
        return
    reference = field(measurement, "validation_gate")
    gate_id = field(reference, "gate_id")
    gate = VALIDATED_GATES.get(gate_id) if isinstance(gate_id, str) else None
    if gate is None:
        raise QuantitativeGateError(GATE_UNAVAILABLE_REASON)
    expected = {
        "gate_version": gate.version, "evidence_sha256": gate.evidence_sha256,
        "analysis_method_id": gate.analysis_method_id,
        "analysis_method_version": gate.analysis_method_version,
        "checkpoint_sha256": gate.checkpoint_sha256,
    }
    if any(field(reference, key) != value for key, value in expected.items()) or any(
        field(measurement, key) != getattr(gate, key)
        for key in ("method_id", "method_version", "unit", "definition", "reference_region")
    ):
        raise QuantitativeGateError("The quantitative gate does not match the measurement method or validation evidence.")
    if provenance is not None and (
        field(reference, "analysis_method_id") != field(provenance, "method_id")
        or field(reference, "analysis_method_version") != field(provenance, "method_version")
        or field(reference, "checkpoint_sha256") != field(provenance, "checkpoint_sha256")
        or field(reference, "source_sha256") != field(field(provenance, "source"), "source_sha256")
    ):
        raise QuantitativeGateError("The quantitative gate does not match the result source or model provenance.")


def require_reportable_result(result):
    """Also handles raw dictionaries and model_construct/mutated model instances."""
    provenance = field(result, "provenance")
    for lesion in field(result, "lesions", None) or []:
        measurements = field(lesion, "measurements")
        for name in ("reference_diameter", "minimum_lumen_diameter", "percentage_narrowing"):
            require_measurement_gate(field(measurements, name), provenance)
