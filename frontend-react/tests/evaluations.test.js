import test from 'node:test';
import assert from 'node:assert/strict';
import { createEvaluationsApi } from '../src/api/evaluations-contract.js';
import { evaluationFixture, evaluationId, indexFixture, runsFixture, sectionsFixture, supplementalFixture } from './evaluation-fixtures.js';
import { evaluationJsonBlob, evaluationCsvBlob } from '../src/lib/exports.js';

const importDocument = () => {
  const row = evaluationFixture();
  return { schema_version: 'offline-evaluation/1.0', metadata: row.identity.metadata, cases: row.cases.cases };
};

test('artifact upload uses multipart bytes, verifies their checksum, and imports only the returned ID', async () => {
  const document = importDocument();
  const blob = new Blob([JSON.stringify(document)], { type: 'application/json' });
  const expectedHash = [...new Uint8Array(await crypto.subtle.digest('SHA-256', await blob.arrayBuffer()))].map(v => v.toString(16).padStart(2, '0')).join('');
  const calls = [];
  const api = createEvaluationsApi({ post: async (path, body, options) => {
    calls.push({ path, body, options });
    if (path.endsWith('/artifacts')) {
      assert.equal(body.get('file').name, 'offline-evaluation.json');
      assert.equal(await body.get('file').text(), await blob.text());
      assert.equal(options.headers['Content-Type'], 'multipart/form-data');
      return { status: 201, data: { id: evaluationId(101), sha256: expectedHash, size_bytes: blob.size, schema_version: 'offline-evaluation/1.0' } };
    }
    return { status: 200, data: evaluationFixture().summary };
  } });
  const upload = await api.upload(blob);
  assert.equal((await api.importArtifact(upload)).source_artifact_id, evaluationId(101));
  assert.deepEqual(calls[1].body, { source_artifact_id: evaluationId(101), metadata: document.metadata });
  assert.equal(calls.length, 2);
});

for (const [name, blob] of [
  ['empty', new Blob([])], ['oversized', new Blob([new Uint8Array(2 * 1024 * 1024 + 1)])],
  ['invalid JSON', new Blob(['{broken'])], ['wrong schema', new Blob(['{"schema_version":"unknown"}'])],
  ['dataset ID used as noncanonical case ID', new Blob([JSON.stringify({ ...importDocument(), cases: [{ case_id: '851' }] })])],
]) test(`invalid upload ${name} never sends a request`, async () => {
  let calls = 0;
  const service = createEvaluationsApi({ post: async () => { calls++; throw new Error('Unexpected request'); } });
  await assert.rejects(service.upload(blob)); assert.equal(calls, 0);
});

test('a mismatched server checksum stops before import and is never retried automatically', async () => {
  let calls = 0;
  const service = createEvaluationsApi({ post: async () => { calls++; return { status: 201,
    data: { id: evaluationId(101), sha256: 'f'.repeat(64), size_bytes: 1, schema_version: 'offline-evaluation/1.0' } }; } });
  await assert.rejects(service.upload(new Blob([JSON.stringify(importDocument())])));
  assert.equal(calls, 1);
});

test('evaluation exports preserve zero, null, exclusions and source/checkpoint identity without mutation', async () => {
  const { summary, cases } = evaluationFixture();
  const before = JSON.stringify({ summary, cases });
  const report = JSON.parse(await evaluationJsonBlob(summary, cases).text());
  assert.equal(report.summary.macro_metrics.dice, 0);
  assert.equal(report.summary.macro_metrics.precision, null);
  assert.equal(report.cases.cases.length, 2);
  assert.equal(report.cases.cases[1].exclusion_reason, 'Synthetic exclusion');
  assert.equal(report.clinical_validation, false);
  assert.equal(report.quantitative_stenosis_available, false);
  const csv = await evaluationCsvBlob(summary, cases).text();
  assert.match(csv, /macro_headline/); assert.match(csv, /case_excluded/);
  assert.match(csv, /"0","0","","0"/);
  assert.match(csv, new RegExp(summary.checkpoint_sha256));
  assert.doesNotMatch(csv, /pooled_micro_separate/);
  assert.equal(JSON.stringify({ summary, cases }), before);
});

test('CSV labels pooled micro separately and neutralizes spreadsheet formulas', async () => {
  const { summary, cases } = evaluationFixture();
  summary.pooled_micro_metrics = { dice: 0, iou: 0, precision: null, recall: 0 };
  cases.cases[0].dataset_case_id = '=1+1';
  const csv = await evaluationCsvBlob(summary, cases).text();
  assert.match(csv, /pooled_micro_separate/);
  assert.match(csv, /"'=1\+1"/);
});

for (const format of [evaluationJsonBlob, evaluationCsvBlob]) {
  for (const mismatch of ['membership', 'checkpoint', 'exclusions', 'numeric_stenosis', 'toJSON_stenosis']) {
    test(`${format.name} rejects ${mismatch} before creating any Blob`, () => {
      const { summary, cases } = evaluationFixture();
      if (mismatch === 'membership') cases.cases[1].case_id = 3;
      if (mismatch === 'checkpoint') { cases.checkpoint_sha256 = 'f'.repeat(64); cases.metadata = structuredClone(cases.metadata); cases.metadata.checkpoint.sha256 = cases.checkpoint_sha256; }
      if (mismatch === 'exclusions') cases.cases[1].exclusion_reason = null;
      const probe = { measurements: { percentage_narrowing: { value: 0, validated: true } } };
      if (mismatch === 'numeric_stenosis') summary.metadata.provenance = probe;
      if (mismatch === 'toJSON_stenosis') summary.metadata.provenance = { toJSON: () => probe };
      const OriginalBlob = globalThis.Blob;
      let blobs = 0;
      globalThis.Blob = class { constructor() { blobs++; } };
      try { assert.throws(() => format(summary, cases)); assert.equal(blobs, 0); }
      finally { globalThis.Blob = OriginalBlob; }
    });
  }
}

const apiFor = (data, calls = []) => createEvaluationsApi({ get: async (path, options) => { calls.push([path, options]); return { data }; } });

test('supplemental read metrics preserve zero/null, coverage and explicit surface-distance abstention', async () => {
  const { summary, cases } = evaluationFixture();
  summary.supplemental_metrics = supplementalFixture(); cases.supplemental_metrics = supplementalFixture();
  assert.equal((await apiFor(summary).summary(summary.id)).supplemental_metrics.macro_metrics.voxel_accuracy, 0);
  assert.equal((await apiFor(cases).cases(cases.id)).supplemental_metrics.macro_metrics.specificity, null);
  const json = JSON.parse(await evaluationJsonBlob(summary, cases).text());
  assert.equal(json.summary.supplemental_metrics.per_case[1].included, false);
  assert.equal(json.summary.supplemental_metrics.surface_distances.hausdorff_distance, null);
  const csv = await evaluationCsvBlob(summary, cases).text();
  assert.match(csv, /voxel_accuracy/); assert.match(csv, /supplemental_macro_denominators/);
  assert.match(csv, /unavailable_not_computed/);
});

for (const [name, change] of [
  ['wrong version', value => { value.version = 'unknown'; }],
  ['null cannot replace a genuine zero', value => { value.macro_metrics.voxel_accuracy = null; }],
  ['negative denominator', value => { value.macro_denominators.voxel_accuracy.undefined_cases = -1; }],
  ['favorable excluded member', value => { value.per_case[1].included = true; }],
  ['changed membership', value => { value.per_case[0].case_id = 3; }],
  ['missing unavailable reason', value => { delete value.per_case[0].unavailable_reasons.specificity; }],
  ['invented surface metric', value => { value.surface_distances.hausdorff_distance = 0; }],
]) test(`supplemental statistics reject ${name}`, async () => {
  const { summary } = evaluationFixture(); summary.supplemental_metrics = supplementalFixture();
  change(summary.supplemental_metrics);
  await assert.rejects(apiFor(summary).summary(summary.id), /Invalid evaluation/);
});

test('exports reject summary/case supplemental evidence mismatch and retain old-API compatibility', async () => {
  const { summary, cases } = evaluationFixture();
  await evaluationJsonBlob(summary, cases).text();
  summary.supplemental_metrics = supplementalFixture();
  assert.throws(() => evaluationJsonBlob(summary, cases), /Supplemental evaluation evidence differs/);
});
test('evaluation listing is bounded and uses only real response records', async () => {
  const calls = [], row = evaluationFixture().identity;
  assert.deepEqual((await apiFor(indexFixture([row]), calls).list()).items, [row]);
  assert.deepEqual(calls, [['/evaluations', { params: { limit: 20, offset: 0 } }]]);
  assert.deepEqual((await apiFor(indexFixture()).list()).items, []);
});
test('summary preserves legitimate zero metrics, nulls and denominator provenance', async () => {
  const { summary } = evaluationFixture();
  assert.deepEqual(await apiFor(summary).summary(summary.id), summary);
  assert.equal(summary.macro_metrics.dice, 0); assert.equal(summary.macro_metrics.precision, null);
});
for (const [name, mutate] of [
  ['wrong identity', (s) => { s.id = evaluationId(8); }],
  ['wrong checkpoint', (s) => { s.checkpoint_sha256 = 'f'.repeat(64); }],
  ['micro as headline', (s) => { s.headline_aggregation = 'pooled_micro'; }],
  ['negative metric', (s) => { s.macro_metrics.dice = -1; }],
  ['missing metric', (s) => { delete s.macro_metrics.recall; }],
  ['nonfinite metric', (s) => { s.macro_metrics.dice = Infinity; }],
  ['contradictory denominator', (s) => { s.macro_denominators.dice.defined_cases = 0; }],
  ['duplicate case', (s) => { s.case_ids = [1,1]; }],
]) test(`summary rejects ${name}`, async () => {
  const { summary } = evaluationFixture(); mutate(summary);
  await assert.rejects(apiFor(summary).summary(evaluationId()), /Invalid evaluation/);
});
test('case endpoint preserves exclusions, nulls and source hashes', async () => {
  const { cases } = evaluationFixture(); assert.deepEqual(await apiFor(cases).cases(cases.id), cases);
});
test('comparison preserves protocol disagreement and requires exact cases', async () => {
  const one = evaluationFixture(1).summary, two = evaluationFixture(2).summary;
  const result = { case_ids: [1,2], evaluations: [one,two], metric_definitions_match: false, reference_artifacts_match: true, exclusions_match: false };
  assert.equal((await apiFor(result).compare([one.id,two.id])).metric_definitions_match, false);
  two.case_ids = [1,3];
  await assert.rejects(apiFor(result).compare([one.id,two.id]), /Invalid evaluation/);
});
test('HTTP 409 case-set conflict is not replaced by a fabricated comparison', async () => {
  const error = Object.assign(new Error('Case sets must match exactly'), { response: { status: 409 } });
  const api = createEvaluationsApi({ get: async () => { throw error; } });
  await assert.rejects(api.compare([evaluationId(1),evaluationId(2)]), (e) => e === error);
});
test('imported model run history stays separate from training execution', async () => {
  const row = evaluationFixture().identity, runs = runsFixture(row);
  assert.deepEqual(await apiFor(runs).runs(row.model_id), runs);
  runs.pagination.next_offset = 1000001;
  await assert.rejects(apiFor(runs).runs(row.model_id), /Invalid evaluation/);
});
test('stenosis sections require explicit unavailable gate status', async () => {
  const value = sectionsFixture(evaluationId());
  assert.deepEqual(await apiFor(value).sections(evaluationId(),1), value);
  value.quantitative_stenosis_available = true;
  await assert.rejects(apiFor(value).sections(evaluationId(),1), /Invalid evaluation/);
});
test('malformed index and duplicates fail closed', async () => {
  const row = evaluationFixture().identity;
  await assert.rejects(apiFor(indexFixture([row,row])).list(), /Invalid evaluation/);
  const data = indexFixture(); data.next_offset = 1000001;
  await assert.rejects(apiFor(data).list(), /Invalid evaluation/);
});
