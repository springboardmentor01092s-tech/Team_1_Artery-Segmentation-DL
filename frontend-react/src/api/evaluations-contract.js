const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const HASH = /^[0-9a-f]{64}$/i;
export const METRICS = Object.freeze(['dice', 'iou', 'precision', 'recall']);
const requireValue = (ok) => { if (!ok) throw new Error('Invalid evaluation API response'); };
const uuid = (value) => { requireValue(typeof value === 'string' && UUID.test(value)); return value; };
const caseIds = (ids) => Array.isArray(ids) && ids.length > 0
  && ids.every((id) => Number.isSafeInteger(id) && id > 0) && new Set(ids).size === ids.length;
function metrics(value) {
  requireValue(value && METRICS.every((key) => value[key] === null
    || typeof value[key] === 'number' && Number.isFinite(value[key]) && value[key] >= 0 && value[key] <= 1));
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
  return row;
}
export function createEvaluationsApi(api) {
  return {
    async list(offset = 0) {
      const { data } = await api.get('/evaluations', { params: { limit: 20, offset } });
      pagination(data); requireValue(Array.isArray(data.items)); data.items.forEach(membership);
      requireValue(data.items.length <= data.limit && new Set(data.items.map((r) => r.id)).size === data.items.length);
      return data;
    },
    async summary(id) { return validateSummary((await api.get(`/evaluations/${uuid(id)}/summary`)).data, id); },
    async cases(id) {
      const { data } = await api.get(`/evaluations/${uuid(id)}/cases`);
      identity(data, id); requireValue(caseIds(data.cases?.map((row) => row.case_id)));
      data.cases.forEach((row) => { metrics(row.metrics); requireValue(HASH.test(row.reference_sha256) && HASH.test(row.prediction_sha256)); });
      return data;
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
