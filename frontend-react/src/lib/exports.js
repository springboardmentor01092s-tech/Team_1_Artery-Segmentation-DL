import { requireMeasurementGate } from "./quantitative-gate.js";
import { toCaseWorkflow } from '../api/cases-contract.js';

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
  if (value.schema_version === "experimental-candidates/1.0"
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
