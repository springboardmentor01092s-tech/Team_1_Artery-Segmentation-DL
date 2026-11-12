import { requireMeasurementGate } from "./quantitative-gate.js";

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
