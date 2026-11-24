import { requireMeasurementGate } from "./quantitative-gate.js";
import { toCaseWorkflow } from '../api/cases-contract.js';
import { METRICS, SUPPLEMENTAL_METRICS, validateSummary as validateEvaluationSummary, validateCases as validateEvaluationCases } from '../api/evaluations-contract.js';

// Export an explicit allowlist; internal storage paths never leave the UI adapter.
export function caseRecord(item) {
  return {
    case_id: item.id,
    case_reference: item.caseCode,
    subject_id: item.patientId,
    study_type: item.studyType,
    modality: item.modality,
    anatomical_region: item.region,
    scan_date: item.scanDate,
    age_years: item.age,
    sex: item.gender,
    notes: item.notes,
    status: item.status,
    has_image: item.hasImage,
    has_volume: item.hasVolume,
    created_at: item.createdAt,
  };
}
export function csvCell(value) {
  const text = String(value ?? "");
  const safe = /^[\s]*[=+\-@]/.test(text) ? `'${text}` : text;
  return `"${safe.replaceAll('"', '""')}"`;
}
export function serializeCsv(records) {
  if (!records.length) return "";
  const keys = Object.keys(records[0]);
  return [
    keys.map(csvCell).join(","),
    ...records.map((row) => keys.map((key) => csvCell(row[key])).join(",")),
  ].join("\r\n");
}

const stenosisMeasurementFields = [
  "reference_diameter", "minimum_lumen_diameter", "percentage_narrowing",
];

function requireExportableMeasurements(value, provenance) {
  if (!value || typeof value !== "object") return;
  if (['simulated-research-assessment/0.1','simulated-research-record/0.1','full-volume-research-profile/0.1','offline-research-evidence/0.1','offline-research-workspace/0.1','verified-offline-research/0.1'].includes(value.schema_version)
      || (Object.hasOwn(value,'sampled_area_mm2') && Object.hasOwn(value,'r1_reference_area_mm2')
        && Object.hasOwn(value,'r2_reference_area_mm2') && Object.hasOwn(value,'comparison'))
      || (value.origin === 'algorithmic_simulation_on_model_derived_mask' && Object.hasOwn(value,'source_evidence_sha256'))
      || (Object.hasOwn(value,'research_measurement') && value.status === 'algorithmically_proposed_unverified')
      || Object.hasOwn(value,'diagnostic_diameter_reduction_percent')
      || (value.origin === 'manual_unverified_research' && Object.hasOwn(value,'diagnostic_diameter_reduction_percent'))) {
    throw new Error('Provisional research assessments cannot enter normal reports. Use the separate source-bound research JSON download.');
  }
  if (['ct-review-note/0.1','independent-lesion-review/0.1','independent-review-submission/0.1','review-submission-amendment/0.1','review-adjudication/0.1','review-adjudication-version/0.1','review-documentation-coverage/0.1'].includes(value.schema_version)) {
    throw new Error('Unverified annotation drafts and private review notes cannot enter normal reports. Use Assigned CT review.');
  }
  if (Object.hasOwn(value,'r1_submission_sha256') && Object.hasOwn(value,'r2_submission_sha256')
      && Object.hasOwn(value,'correspondences') && Object.hasOwn(value,'resolutions')) {
    throw new Error('Unverified adjudication records cannot enter ordinary reports. Use the separate restricted review workspace.');
  }
  if (value.schema_version === 'lesion-annotation-workspace/0.1'
      || (Object.hasOwn(value, 'draft_id') && Object.hasOwn(value, 'center_ijk')
        && Object.hasOwn(value, 'minimum_lumen_diameter_mm') && Object.hasOwn(value, 'percentage_narrowing'))) {
    throw new Error('Unverified annotation drafts cannot be included in normal reports. Use the separate, source-bound draft download.');
  }
  if (["experimental-candidates/1.0","experimental-automatic-candidates/0.1","automatic-branch-evidence/0.1","experimental-branch-graph/0.1"].includes(value.schema_version)
      || (value.kind === "experimental_candidate" && Object.hasOwn(value, "candidate_id")
        && Object.hasOwn(value, "sample_ijk") && Object.hasOwn(value, "world_ras_mm"))) {
    throw new Error("Experimental candidate previews cannot be included in ordinary reports or metadata exports. Use the separate standalone research-preview JSON workflow.");
  }
  const context = Object.hasOwn(value, "provenance") ? value.provenance : provenance;
  // These are the contract's lesion.measurements fields, not arbitrary numeric
  // properties or segmentation/evaluation metrics. Walk wrappers and arrays too.
  const measurements = value.measurements;
  if (measurements && typeof measurements === "object") {
    for (const field of stenosisMeasurementFields) {
      if (!Object.hasOwn(measurements, field)) continue;
      const measurement = measurements[field];
      if (measurement?.value === null) {
        const reason = measurement.unavailable_reason;
        if (typeof reason?.code !== "string" || !reason.code.trim()
            || typeof reason.message !== "string" || !reason.message.trim()) {
          throw new Error("Unavailable stenosis measurements require an explicit reason.");
        }
      }
      requireMeasurementGate(measurement, context);
    }
  }
  for (const child of Object.values(value)) requireExportableMeasurements(child, context);
}

function exportJson(value) {
  // Check the exact detached JSON snapshot that will be emitted, including any
  // getters/toJSON transformations. Never reserialize the mutable input afterward.
  const content = JSON.stringify(value, null, 2);
  requireExportableMeasurements(JSON.parse(content));
  return content;
}

function evaluationSnapshot(summary, cases) {
  // Validate the exact detached export, including toJSON hooks. Both numeric
  // stenosis guards and the evaluation contracts apply before any Blob exists.
  const report = JSON.parse(exportJson({ schema_version: 'evaluation-report/1.0',
    document_type: 'research_segmentation_evaluation', clinical_validation: false,
    quantitative_stenosis_available: false, headline_aggregation: 'macro_unweighted_per_case',
    limitation: 'Research segmentation evaluation; not clinical validation or quantitative stenosis.',
    summary, cases }));
  validateEvaluationSummary(report.summary);
  validateEvaluationCases(report.cases, report.summary.id);
  const ordered = ids => [...ids].sort((a, b) => a - b).join(',');
  if (ordered(report.summary.case_ids) !== ordered(report.cases.cases.map(row => row.case_id))
      || ['source_artifact_id', 'checkpoint_sha256', 'model_id', 'threshold'].some(key => report.summary[key] !== report.cases[key])
      || JSON.stringify(report.summary.metadata) !== JSON.stringify(report.cases.metadata)) {
    throw new Error('Evaluation summary and cases do not describe the same immutable evidence. Refresh before exporting.');
  }
  if (JSON.stringify(report.summary.supplemental_metrics ?? null) !== JSON.stringify(report.cases.supplemental_metrics ?? null)) {
    throw new Error('Supplemental evaluation evidence differs. Refresh before exporting.');
  }
  const excluded = report.cases.cases.filter(row => row.exclusion_reason !== null);
  if (report.summary.included_case_count !== report.cases.cases.length - excluded.length
      || !Array.isArray(report.summary.exclusions) || report.summary.exclusions.length !== excluded.length
      || excluded.some(row => !report.summary.exclusions.some(item => item.case_id === row.case_id && item.reason === row.exclusion_reason))) {
    throw new Error('Evaluation exclusions differ. No export was created.');
  }
  return report;
}

export function evaluationJsonBlob(summary, cases) {
  return new Blob([JSON.stringify(evaluationSnapshot(summary, cases), null, 2)], { type: 'application/json;charset=utf-8' });
}

export function evaluationCsvBlob(summary, cases) {
  const report = evaluationSnapshot(summary, cases);
  const base = { evaluation_id: report.summary.id, model_id: report.summary.model_id,
    checkpoint_sha256: report.summary.checkpoint_sha256, source_artifact_id: report.summary.source_artifact_id,
    threshold: report.summary.threshold, metric_definition_version: report.summary.metadata.metric_definitions.version,
    clinical_validation: false };
  const record = (type, values, row = {}) => ({ ...base, record_type: type,
    case_id: row.case_id ?? null, dataset_case_id: row.dataset_case_id ?? null,
    exclusion_reason: row.exclusion_reason ?? null,
    ...Object.fromEntries(METRICS.map(key => [key, values[key]])),
    ...Object.fromEntries(SUPPLEMENTAL_METRICS.map(key => [key,
      (type === 'macro_headline' ? report.summary.supplemental_metrics?.macro_metrics
        : type === 'pooled_micro_separate' ? report.summary.supplemental_metrics?.pooled_micro_metrics
          : report.summary.supplemental_metrics?.per_case.find(item => item.case_id === row.case_id)?.metrics)?.[key] ?? null])),
    supplemental_macro_denominators: type === 'macro_headline' && report.summary.supplemental_metrics
      ? JSON.stringify(report.summary.supplemental_metrics.macro_denominators) : null,
    surface_distances_status: 'unavailable_not_computed',
    macro_denominators: type === 'macro_headline' ? JSON.stringify(report.summary.macro_denominators) : null,
    included_case_count: report.summary.included_case_count, total_case_count: report.summary.case_count,
    reference_sha256: row.reference_sha256 ?? null, prediction_sha256: row.prediction_sha256 ?? null,
    zero_denominator: 'null; CSV empty cell, never imputed as zero' });
  const rows = [record('macro_headline', report.summary.macro_metrics)];
  if (report.summary.pooled_micro_metrics !== null) rows.push(record('pooled_micro_separate', report.summary.pooled_micro_metrics));
  rows.push(...report.cases.cases.map(row => record(row.exclusion_reason === null ? 'case_included' : 'case_excluded', row.metrics, row)));
  return new Blob(['\uFEFF', serializeCsv(rows)], { type: 'text/csv;charset=utf-8' });
}

// Keep the report allowlist and independently enforce the measurement policy at
// the export boundary, even for direct callers that bypass the API validator.
export function reportJsonBlob(report) {
  return new Blob([exportJson({schema_version:report.schema_version,document_type:report.document_type,generated_at:report.generated_at,
    case:report.case,analysis:report.analysis,report_state:report.report_state,unavailable_reason:report.unavailable_reason,
    result:report.result,explanations:report.explanations,limitations:report.limitations})],{type:'application/json;charset=utf-8'});
}
export function downloadRecords(items, format) {
  const records = items.map(caseRecord);
  const content =
    format === "json"
      ? exportJson(
          {
            exported_at: new Date().toISOString(),
            document_type: "research_case_metadata",
            analysis_available: false,
            cases: records,
          },
        )
      : serializeCsv(records);
  const blob = new Blob([format === "csv" ? "\uFEFF" : "", content], {
    type:
      format === "json"
        ? "application/json;charset=utf-8"
        : "text/csv;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `vascuai-case-${items.length === 1 ? items[0].id : "records"}.${format}`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function downloadCaseWorkflow(workflow) {
  // Validate the detached serialized snapshot before allowlisting, so a toJSON
  // hook or an unexpected nested measurement cannot bypass any export guard.
  const data = JSON.parse(exportJson(workflow));
  toCaseWorkflow(data, data?.case_id);
  const pick = (value, keys) => value === null ? null : Object.fromEntries(keys.map(key => [key, value[key]]));
  const hashes = ['source_sha256', 'checkpoint_sha256', 'mask_sha256', 'probabilities_sha256', 'threshold'];
  const runKeys = ['segmentation_result_id', 'created_at', ...hashes];
  const reviewKeys = ['id', 'case_id', 'segmentation_result_id', 'reviewer_id', 'reviewer_role', 'reviewed_at',
    'outcome', 'note', 'current', 'scope', ...hashes];
  const safe = { case_id:data.case_id, case_status:data.case_status, research_only:true, clinical_validation:false,
    model_analysis:{available:data.model_analysis.available,reason:data.model_analysis.reason,run:pick(data.model_analysis.run,runKeys)},
    review:pick(data.review,reviewKeys), review_history:data.review_history.map(review=>pick(review,reviewKeys)),
    review_requires_new_run:data.review_requires_new_run };
  const content = exportJson({ document_type: 'research_case_workflow', exported_at: new Date().toISOString(),
    clinical_validation: false, workflow:safe });
  const blob = new Blob([content], { type: 'application/json;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `vascuai-case-${workflow.case_id}-workflow.json`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
