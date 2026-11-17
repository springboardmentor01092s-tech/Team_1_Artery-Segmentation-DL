// Independently reviewed gate definitions only. No gate currently qualifies.
// Never trust a supplied gate ID, evidence digest or validated=true flag alone.
const validatedGates = Object.freeze(Object.create(null));
export const GATE_UNAVAILABLE_REASON = 'No validated quantitative stenosis gate is registered; measurement unavailable.';

export function requireMeasurementGate(measurement, provenance) {
  if (measurement?.value === null) return;
  const reference = measurement?.validation_gate;
  const gate = validatedGates[reference?.gate_id];
  if (!gate) throw new Error(GATE_UNAVAILABLE_REASON);
  if (reference.gate_version !== gate.version || reference.evidence_sha256 !== gate.evidence_sha256
    || ['method_id', 'method_version', 'unit', 'definition', 'reference_region'].some(key => measurement[key] !== gate[key])
    || ['analysis_method_id', 'analysis_method_version', 'checkpoint_sha256'].some(key => reference[key] !== gate[key])
    || reference.analysis_method_id !== provenance?.method_id
    || reference.analysis_method_version !== provenance?.method_version
    || reference.checkpoint_sha256 !== provenance?.checkpoint_sha256
    || reference.source_sha256 !== provenance?.source?.source_sha256) {
    throw new Error('The quantitative gate does not match the measurement method, evidence or source provenance.');
  }
}

export function measurementPresentation(measurement, provenance) {
  if (measurement?.value === null) return { reportable: false, text: `Unavailable: ${measurement.unavailable_reason?.message || GATE_UNAVAILABLE_REASON}` };
  try {
    requireMeasurementGate(measurement, provenance);
    return { reportable: true, text: `${measurement.value} ${measurement.unit}` };
  } catch {
    return { reportable: false, text: `Unavailable: ${GATE_UNAVAILABLE_REASON}` };
  }
}
