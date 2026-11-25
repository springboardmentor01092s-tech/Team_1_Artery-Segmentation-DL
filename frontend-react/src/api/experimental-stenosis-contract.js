const SHAPE = [24, 24, 24];
const fail = () => { throw new Error('Malformed synthetic research response; no result was accepted.'); };
const finite = x => typeof x === 'number' && Number.isFinite(x);
const forbiddenTruthKeys = new Set(['class_label','synthetic_class_label','synthetic_geometry_ground_truth','true_label','ground_truth_label']);
function containsGroundTruth(value) {
  if (!value || typeof value !== 'object') return false;
  if (Array.isArray(value)) return value.some(containsGroundTruth);
  return Object.entries(value).some(([key, nested]) => forbiddenTruthKeys.has(key) || containsGroundTruth(nested));
}

export function validateSyntheticStatus(value) {
  if (!value || typeof value.available !== 'boolean' || typeof value.scope !== 'string'
      || value.scope !== 'synthetic_generated_phantoms_only' || value.clinical_gate_authorized !== false
      || value.training_release_authorized !== false
      || (value.reason !== null && typeof value.reason !== 'string')) fail();
  return value;
}

export function validateSyntheticSample(value) {
  if (!value || value.schema_version !== 'synthetic-stenosis-sample/0.2'
      || !Number.isSafeInteger(value.sample_id) || value.sample_id < 0
      || containsGroundTruth(value)
      || !Array.isArray(value.shape) || value.shape.some((n, i) => n !== SHAPE[i])
      || value.clinical_validation !== false || value.clinical_gate_authorized !== false
      || value.training_release_authorized !== false || typeof value.notice !== 'string'
      || !Array.isArray(value.middle_slice) || value.middle_slice.length !== SHAPE[0]
      || value.middle_slice.some(row => !Array.isArray(row) || row.length !== SHAPE[1] || row.some(x => !finite(x) || x < 0 || x > 1))
      || value.provenance?.source !== 'vascuai-synthetic-vessel-phantom'
      || !/^[a-f0-9]{64}$/.test(value.provenance?.volume_sha256 || '')) fail();
  return value;
}

export function validateSyntheticAnalysis(value) {
  const cam = value?.explainability, model = value?.model, geometry = value?.geometry_analysis;
  if (!value || value.schema_version !== 'experimental-stenosis-analysis/0.3'
      || value.status !== 'completed_synthetic_research_only'
      || value.clinical_validation !== false || value.clinical_gate_authorized !== false
      || value.training_release_authorized !== false || !/^[a-f0-9]{64}$/.test(value.provenance?.volume_sha256 || '')
      || value.provenance?.patient_case_id !== null || value.provenance?.dataset_case_id !== null
      || containsGroundTruth(value)
      || typeof value.provenance?.synthetic_sample_id !== 'number'
      || typeof model?.model_id !== 'string' || !/^[a-f0-9]{64}$/.test(model?.checkpoint_sha256 || '')
      || model?.clinical_performance_claim !== false || model?.score_semantics !== 'uncalibrated_softmax_probability_not_clinical_confidence'
      || !Array.isArray(model?.class_probabilities_uncalibrated) || model.class_probabilities_uncalibrated.length !== 5
      || model.class_probabilities_uncalibrated.some(p => !finite(p) || p < 0 || p > 1)
      || Math.abs(model.class_probabilities_uncalibrated.reduce((a, b) => a + b, 0) - 1) > 1e-4
      || cam?.method !== '3d-cnn-grad-cam' || cam?.scope !== 'synthetic_generated_phantom_only'
      || JSON.stringify(cam?.shape) !== JSON.stringify(SHAPE) || !Array.isArray(cam?.heatmap_values)
      || cam.heatmap_values.length !== SHAPE.reduce((a, b) => a * b, 1)
      || cam.heatmap_values.some(x => !finite(x) || x < 0 || x > 1.00001)
      || !Array.isArray(geometry?.candidates) || !Number.isSafeInteger(geometry?.candidate_count)
      || geometry.candidate_count !== geometry.candidates.length) fail();
  const metrics = geometry.metrics, measurementProvenance = geometry.measurement_provenance;
  if (measurementProvenance?.scope !== 'synthetic_generated_phantom_only'
      || measurementProvenance.input_volume_sha256 !== value.provenance.volume_sha256
      || typeof measurementProvenance.method !== 'string'
      || typeof measurementProvenance.axis_source !== 'string'
      || measurementProvenance.clinical_gate_authorized !== false
      || measurementProvenance.training_release_authorized !== false
      || !Array.isArray(measurementProvenance.provisional_severity_thresholds_percent)
      || measurementProvenance.provisional_severity_thresholds_percent.length !== 4
      || measurementProvenance.provisional_severity_thresholds_percent.some((x, i, values) =>
        !finite(x) || x < 0 || x > 100 || (i > 0 && values[i - 1] >= x))
      || !finite(metrics?.reference_radius_synthetic_units) || metrics.reference_radius_synthetic_units <= 0
      || !finite(metrics?.minimum_radius_synthetic_units) || metrics.minimum_radius_synthetic_units <= 0
      || (metrics.estimated_percentage_narrowing_synthetic_only !== null
        && (!finite(metrics.estimated_percentage_narrowing_synthetic_only)
          || metrics.estimated_percentage_narrowing_synthetic_only < 0
          || metrics.estimated_percentage_narrowing_synthetic_only > 100))
      || typeof metrics.measurement_availability !== 'string'
      || (metrics.measurement_confidence !== null && !finite(metrics.measurement_confidence))
      || (metrics.measurement_uncertainty !== null && !finite(metrics.measurement_uncertainty))
      || (metrics.measurement_confidence !== null || metrics.measurement_uncertainty !== null)
      || !Array.isArray(metrics.severity_thresholds_percent_synthetic_only)
      || metrics.severity_thresholds_percent_synthetic_only.length !== 4) fail();
  for (const candidate of geometry.candidates) {
    if (typeof candidate.candidate_id !== 'string' || candidate.status !== 'experimental_candidate'
        || candidate.location?.coordinate_space !== 'synthetic_IJK_voxel_units'
        || !Array.isArray(candidate.location.center_ijk) || candidate.location.center_ijk.length !== 3
        || candidate.location.center_ijk.some(x => !finite(x))
        || candidate.measurements?.quality !== 'synthetic_geometry_only_unvalidated'
        || candidate.measurements?.measurement_availability !== 'estimated_synthetic_only'
        || candidate.measurements?.measurement_confidence !== null
        || candidate.measurements?.measurement_uncertainty !== null
        || !finite(candidate.measurements?.minimum_radius_synthetic_units)
        || !finite(candidate.measurements?.reference_radius_synthetic_units)
        || candidate.measurements.minimum_radius_synthetic_units <= 0
        || candidate.measurements.reference_radius_synthetic_units < candidate.measurements.minimum_radius_synthetic_units
        || (candidate.measurements.estimated_percentage_narrowing_synthetic_only !== null
          && (!finite(candidate.measurements.estimated_percentage_narrowing_synthetic_only)
            || candidate.measurements.estimated_percentage_narrowing_synthetic_only < 0
            || candidate.measurements.estimated_percentage_narrowing_synthetic_only > 100))) fail();
  }
  return value;
}
