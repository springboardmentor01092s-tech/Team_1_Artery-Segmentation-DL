// Synthetic contract fixtures, never imported by application source.
export const evaluationId = (n = 1) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`;
export function evaluationFixture(n = 1) {
  const metadata = {
    model: { id: 'synthetic-unet', architecture: 'SyntheticTestModel', display_name: 'Synthetic evaluation fixture' },
    checkpoint: { sha256: 'a'.repeat(64), training_run_id: 'synthetic-unresolved-reference', reported_training_steps: null },
    threshold: 0.7,
    validation_split_source: { dataset: 'synthetic-only', manifest_sha256: 'b'.repeat(64), workbook_sha256: null, sheet: null, split_column: 'synthetic', split: 'Val' },
    metric_definitions: { version: 'binary-voxel/1.0', reference_foreground: 'binary label 1', prediction_foreground: 'binary label 1', zero_denominator: 'null' },
    provenance: { source: 'synthetic-test-only', original_training_run_id: null, identity_status: 'historical_provenance_unresolved' },
  };
  const identity = { id: evaluationId(n), source_artifact_id: evaluationId(n+100), model_id: metadata.model.id,
    model_run_id: evaluationId(50), checkpoint_sha256: metadata.checkpoint.sha256, threshold: metadata.threshold,
    metadata, created_at: '2026-01-01T00:00:00Z' };
  const zero = { dice: 0, iou: 0, precision: null, recall: 0 };
  const summary = { ...identity, case_ids: [1, 2], case_count: 2, included_case_count: 1,
    exclusions: [{ case_id: 2, reason: 'Synthetic exclusion' }], headline_aggregation: 'macro_unweighted_per_case',
    macro_metrics: { ...zero }, macro_denominators: Object.fromEntries(Object.entries(zero).map(([k,v]) => [k, { defined_cases: v === null ? 0 : 1, undefined_cases: v === null ? 1 : 0 }])),
    pooled_micro_metrics: null, pooled_status: 'unavailable_without_complete_included_confusion_counts',
    metric_formulas: { dice: '2TP/(2TP+FP+FN)', iou: 'TP/(TP+FP+FN)', precision: 'TP/(TP+FP)', recall: 'TP/(TP+FN)' },
    zero_denominator: 'null', undefined_macro_policy: 'omit_undefined_per_metric_and_report_count' };
  const cases = { ...identity, metric_definitions: metadata.metric_definitions, metric_formulas: summary.metric_formulas,
    undefined_macro_policy: summary.undefined_macro_policy, cases: [1,2].map((id) => ({ case_id: id, dataset_case_id: `synthetic-${id}`,
      reference_sha256: 'd'.repeat(64), prediction_sha256: 'e'.repeat(64), metrics: { ...zero }, confusion_counts: null,
      exclusion_reason: id === 2 ? 'Synthetic exclusion' : null, mask_provenance: { origin: 'reference_annotation', mask_sha256: 'd'.repeat(64) }, sections: [] })) };
  return { identity: { ...identity, case_ids: [1,2] }, summary, cases };
}
export function supplementalFixture() {
  const values = { voxel_accuracy: 0, specificity: null, sensitivity: 0, f1_score: 0 };
  const names = Object.keys(values);
  return { version: 'confusion-derived/1.0', source: 'stored_case_confusion_counts', zero_denominator: 'null',
    macro_metrics: { ...values }, pooled_micro_metrics: { ...values },
    pooled_unavailable_reasons: { specificity: 'zero_denominator' },
    macro_denominators: Object.fromEntries(names.map(key => [key, { defined_cases: values[key] === null ? 0 : 1, undefined_cases: values[key] === null ? 1 : 0 }])),
    formulas: { voxel_accuracy: '(TP+TN)/(TP+TN+FP+FN)', specificity: 'TN/(TN+FP)', sensitivity: 'TP/(TP+FN)', f1_score: '2TP/(2TP+FP+FN)' },
    per_case: [{ case_id: 1, included: true, exclusion_reason: null, metrics: { ...values }, unavailable_reasons: { specificity: 'zero_denominator' } },
      { case_id: 2, included: false, exclusion_reason: 'Synthetic exclusion', metrics: Object.fromEntries(names.map(key => [key, null])),
        unavailable_reasons: Object.fromEntries(names.map(key => [key, 'confusion_counts_unavailable'])) }],
    surface_distances: { status: 'unavailable_not_computed', hausdorff_distance: null, average_surface_distance: null, units: null,
      reason: 'Surface geometry is not contained in confusion counts.' } };
}
export const indexFixture = (rows = []) => ({ items: rows, limit: 20, offset: 0, next_offset: null, offset_limit_reached: false });
export function runsFixture(row) {
  return { model: row.metadata.model, training_runs: [{ id: row.model_run_id, training_run_id: row.metadata.checkpoint.training_run_id,
    checkpoint_sha256: row.checkpoint_sha256, reported_training_steps: null, record_origin: 'imported_offline_evaluation_metadata' }],
    evaluations: [row], pagination: { limit: 20, offset: 0, next_offset: null, offset_limit_reached: false, returned_evaluations: 1, returned_training_runs: 1 } };
}
export function sectionsFixture(id, caseId = 1) {
  return { evaluation_id: id, case_id: caseId, source_artifact_id: evaluationId(101),
    measurement_status: 'measurement_unavailable_no_validated_gate', validated_resolution_gate: null,
    quantitative_stenosis_available: false, mask_provenance: { origin: 'reference_annotation', mask_sha256: 'd'.repeat(64) },
    sections: [], section_data_status: 'unavailable_no_section_records', provenance: {} };
}
