const sha = value => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);

export function validateRealVolumeResearch(value) {
  if (!value || value.schema_version !== 'real-volume-research/0.1'
      || !['profile_only', 'abstained'].includes(value.status)
      || value.candidate_status !== 'unavailable_mask_semantics_unverified'
      || value.clinical_validation !== false || value.clinical_gate_authorized !== false
      || value.training_release_authorized !== false || !Array.isArray(value.candidates)
      || value.candidates.length !== 0 || !value.measurements
      || value.measurements.estimated_percentage_narrowing !== null
      || value.measurements.provisional_severity !== null
      || !value.provenance || !sha(value.provenance.ct_sha256)
      || !sha(value.provenance.mask_file_sha256)
      || value.provenance.persisted !== false || value.provenance.synthetic_model_used !== false) {
    throw new Error('Real-volume response failed its research-only safety contract.');
  }
  return value;
}
