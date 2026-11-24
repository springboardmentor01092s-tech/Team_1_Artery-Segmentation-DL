const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const HASH = /^[0-9a-f]{64}$/i;
export const METRICS = Object.freeze(['dice', 'iou', 'precision', 'recall']);
export const SUPPLEMENTAL_METRICS = Object.freeze(['voxel_accuracy', 'specificity', 'sensitivity', 'f1_score']);
export const MAX_EVALUATION_BYTES = 2 * 1024 * 1024;
const requireValue = (ok) => { if (!ok) throw new Error('Invalid evaluation API response'); };
const uuid = (value) => { requireValue(typeof value === 'string' && UUID.test(value)); return value; };
const caseIds = (ids) => Array.isArray(ids) && ids.length > 0
  && ids.every((id) => Number.isSafeInteger(id) && id > 0) && new Set(ids).size === ids.length;
function metrics(value) {
  requireValue(value && METRICS.every((key) => value[key] === null
    || typeof value[key] === 'number' && Number.isFinite(value[key]) && value[key] >= 0 && value[key] <= 1));
}
function supplemental(value, ids, exclusions) {
  if (value == null) return; // Explicit backward compatibility with older APIs.
  const included = ids.length - exclusions.size;
  requireValue([...exclusions].every(([id, reason]) => ids.includes(id) && typeof reason === 'string' && reason.trim().length > 0));
  requireValue(value.version === 'confusion-derived/1.0' && value.source === 'stored_case_confusion_counts'
    && value.zero_denominator === 'null' && Array.isArray(value.per_case) && value.per_case.length === ids.length
    && new Set(value.per_case.map(row => row.case_id)).size === ids.length);
  const values = object => requireValue(object && SUPPLEMENTAL_METRICS.every(key => object[key] === null
    || typeof object[key] === 'number' && Number.isFinite(object[key]) && object[key] >= 0 && object[key] <= 1));
  const unavailable = (object, reasons) => {
    requireValue(reasons && typeof reasons === 'object' && !Array.isArray(reasons));
    const allowed = ['confusion_counts_unavailable', 'true_negative_count_unavailable', 'zero_denominator', 'no_included_cases', 'incomplete_included_confusion_counts'];
    requireValue(Object.keys(reasons).every(key => SUPPLEMENTAL_METRICS.includes(key) && allowed.includes(reasons[key])));
    for (const key of SUPPLEMENTAL_METRICS) requireValue(object[key] === null ? typeof reasons[key] === 'string' : !Object.hasOwn(reasons, key));
  };
  values(value.macro_metrics); values(value.pooled_micro_metrics);
  unavailable(value.pooled_micro_metrics, value.pooled_unavailable_reasons);
  value.per_case.forEach(row => {
    requireValue(ids.includes(row.case_id) && row.included === !exclusions.has(row.case_id)
      && row.exclusion_reason === (exclusions.get(row.case_id) ?? null));
    values(row.metrics); unavailable(row.metrics, row.unavailable_reasons);
  });
  for (const key of SUPPLEMENTAL_METRICS) {
    const denominator = value.macro_denominators?.[key];
    const recorded = value.per_case.filter(row => row.included && row.metrics[key] !== null).map(row => row.metrics[key]);
    requireValue(denominator && Number.isInteger(denominator.defined_cases) && Number.isInteger(denominator.undefined_cases)
      && denominator.defined_cases >= 0 && denominator.undefined_cases >= 0
      && denominator.defined_cases === recorded.length
      && denominator.undefined_cases === included - recorded.length
      && (value.macro_metrics[key] === null) === (recorded.length === 0)
      && (recorded.length === 0 ? value.macro_metrics[key] === null
        : Math.abs(value.macro_metrics[key] - recorded.reduce((a,b) => a+b, 0)/recorded.length) <= 1e-12));
  }
  const distances = value.surface_distances;
  requireValue(distances?.status === 'unavailable_not_computed' && distances.hausdorff_distance === null
    && distances.average_surface_distance === null && distances.units === null
    && typeof distances.reason === 'string' && distances.reason.trim().length > 0);
}
function identity(row, expected) {
  requireValue(row && uuid(row.id) && (!expected || row.id === expected));
  uuid(row.source_artifact_id);
  requireValue(HASH.test(row.checkpoint_sha256) && typeof row.model_id === 'string' && row.model_id.length > 0
    && row.metadata?.checkpoint?.sha256 === row.checkpoint_sha256
    && row.metadata?.model?.id === row.model_id
    && row.threshold === row.metadata?.threshold
    && Number.isFinite(row.threshold) && row.threshold >= 0 && row.threshold <= 1);
  return row;
}
function membership(row) { identity(row); requireValue(caseIds(row.case_ids)); return row; }
function pagination(value) {
  requireValue(Number.isInteger(value.offset) && value.offset >= 0 && value.offset <= 1000000
    && Number.isInteger(value.limit) && value.limit > 0 && value.limit <= 100
    && (value.next_offset === null || Number.isInteger(value.next_offset)
      && value.next_offset > value.offset && value.next_offset <= 1000000)
    && typeof value.offset_limit_reached === 'boolean');
}
export function validateSummary(row, expected) {
  identity(row, expected);
  requireValue(caseIds(row.case_ids) && row.case_count === row.case_ids.length
    && row.headline_aggregation === 'macro_unweighted_per_case'
    && Number.isInteger(row.included_case_count) && row.included_case_count >= 0
    && row.included_case_count <= row.case_count && row.zero_denominator === 'null');
  metrics(row.macro_metrics);
  if (row.pooled_micro_metrics !== null) metrics(row.pooled_micro_metrics);
  for (const key of METRICS) {
    const d = row.macro_denominators?.[key];
    requireValue(d && Number.isInteger(d.defined_cases) && d.defined_cases >= 0
      && Number.isInteger(d.undefined_cases) && d.undefined_cases >= 0
      && d.defined_cases + d.undefined_cases === row.included_case_count
      && (d.defined_cases === 0) === (row.macro_metrics[key] === null));
  }
  if (row.supplemental_metrics != null) {
    requireValue(Array.isArray(row.exclusions) && new Set(row.exclusions.map(item => item.case_id)).size === row.exclusions.length
      && row.included_case_count === row.case_ids.length - row.exclusions.length);
    supplemental(row.supplemental_metrics, row.case_ids, new Map(row.exclusions.map(item => [item.case_id, item.reason])));
  }
  return row;
}
export function validateCases(data, expected) {
  identity(data, expected); requireValue(caseIds(data.cases?.map((row) => row.case_id)));
  data.cases.forEach((row) => {
    metrics(row.metrics);
    requireValue(HASH.test(row.reference_sha256) && HASH.test(row.prediction_sha256)
      && (row.exclusion_reason === null || typeof row.exclusion_reason === 'string' && row.exclusion_reason.trim().length > 0));
  });
  supplemental(data.supplemental_metrics, data.cases.map(row => row.case_id),
    new Map(data.cases.filter(row => row.exclusion_reason !== null).map(row => [row.case_id, row.exclusion_reason])));
  return data;
}
export function createEvaluationsApi(api) {
  return {
    async upload(file) {
      if (!(file instanceof Blob) || file.size === 0 || file.size > MAX_EVALUATION_BYTES) {
        throw new Error('Choose a nonempty evaluation JSON file at most 2 MiB. No upload was sent.');
      }
      const bytes = await file.arrayBuffer();
      let document;
      try { document = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes)); }
      catch { throw new Error('Choose a readable UTF-8 evaluation JSON document. No upload was sent.'); }
      requireValue(document?.schema_version === 'offline-evaluation/1.0' && document.metadata
        && caseIds(document.cases?.map(row => row.case_id)));
      const expectedHash = [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))]
        .map(value => value.toString(16).padStart(2, '0')).join('');
      const body = new FormData();
      body.append('file', new Blob([bytes], { type: 'application/json' }), 'offline-evaluation.json');
      // Shared Axios adds authentication and its browser-generated multipart
      // boundary. Never send JSON as an arbitrary source_artifact_id.
      const response = await api.post('/evaluations/artifacts', body, { headers: { 'Content-Type': 'multipart/form-data' } });
      const artifact = response.data;
      requireValue(response.status === 201 && artifact?.schema_version === 'offline-evaluation/1.0'
        && uuid(artifact.id) && artifact.sha256 === expectedHash && artifact.size_bytes === bytes.byteLength);
      return { artifact, metadata: document.metadata, case_ids: document.cases.map(row => row.case_id) };
    },
    async importArtifact(upload) {
      uuid(upload?.artifact?.id);
      const response = await api.post('/evaluations/import', {
        source_artifact_id: upload.artifact.id, metadata: upload.metadata,
      });
      requireValue(response.status === 200 || response.status === 201);
      const summary = validateSummary(response.data);
      requireValue(summary.source_artifact_id === upload.artifact.id
        && summary.checkpoint_sha256 === upload.metadata?.checkpoint?.sha256
        && summary.threshold === upload.metadata?.threshold
        && [...summary.case_ids].sort((a,b) => a-b).join(',') === [...upload.case_ids].sort((a,b) => a-b).join(','));
      return summary;
    },
    async list(offset = 0) {
      const { data } = await api.get('/evaluations', { params: { limit: 20, offset } });
      pagination(data); requireValue(Array.isArray(data.items)); data.items.forEach(membership);
      requireValue(data.items.length <= data.limit && new Set(data.items.map((r) => r.id)).size === data.items.length);
      return data;
    },
    async summary(id) { return validateSummary((await api.get(`/evaluations/${uuid(id)}/summary`)).data, id); },
    async cases(id) {
      const { data } = await api.get(`/evaluations/${uuid(id)}/cases`);
      return validateCases(data, id);
    },
    async compare(ids) {
      requireValue(ids.length >= 2 && ids.length <= 10 && new Set(ids).size === ids.length);
      ids.forEach(uuid);
      const { data } = await api.get('/evaluations/compare', { params: { ids: ids.join(',') } });
      requireValue(caseIds(data.case_ids) && Array.isArray(data.evaluations) && data.evaluations.length === ids.length);
      const expected = [...data.case_ids].sort((a, b) => a - b).join(',');
      data.evaluations.forEach((row) => { validateSummary(row); requireValue(ids.includes(row.id)
        && [...row.case_ids].sort((a, b) => a - b).join(',') === expected); });
      requireValue(new Set(data.evaluations.map((row) => row.id)).size === ids.length);
      for (const flag of ['metric_definitions_match', 'reference_artifacts_match', 'exclusions_match']) requireValue(typeof data[flag] === 'boolean');
      return data;
    },
    async runs(modelId, offset = 0) {
      const { data } = await api.get(`/models/${encodeURIComponent(modelId)}/runs`, { params: { limit: 20, offset } });
      requireValue(data.model?.id === modelId && Array.isArray(data.training_runs) && Array.isArray(data.evaluations));
      data.evaluations.forEach(membership); pagination(data.pagination);
      return data;
    },
    async sections(id, caseId) {
      requireValue(Number.isSafeInteger(caseId) && caseId > 0);
      const { data } = await api.get(`/stenosis/evaluations/${uuid(id)}/cases/${caseId}/sections`);
      requireValue(data.evaluation_id === id && data.case_id === caseId
        && data.measurement_status === 'measurement_unavailable_no_validated_gate'
        && data.quantitative_stenosis_available === false && data.validated_resolution_gate === null);
      return data;
    },
  };
}
