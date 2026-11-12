import test from 'node:test';
import assert from 'node:assert/strict';
import { createEvaluationsApi } from '../src/api/evaluations-contract.js';
import { evaluationFixture, evaluationId, indexFixture, runsFixture, sectionsFixture } from './evaluation-fixtures.js';

const apiFor = (data, calls = []) => createEvaluationsApi({ get: async (path, options) => { calls.push([path, options]); return { data }; } });
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
