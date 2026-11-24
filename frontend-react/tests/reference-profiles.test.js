import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { validateReferenceBytes, createReferenceProfilesApi, REFERENCE_GATE } from '../src/api/reference-profiles-contract.js';

test('supplied approval flags and hashes cannot authorize changed bytes', async () => {
  for (const value of [0, 37, null]) {
    const forged = { validated: true, gate_id: REFERENCE_GATE.id, sha256: REFERENCE_GATE.artifactSha256, diameter_mm: value };
    await assert.rejects(validateReferenceBytes(new TextEncoder().encode(JSON.stringify(forged))), /identity differs/);
  }
});

test('dedicated authenticated adapter requests raw bytes and enforces identity', async () => {
  const calls = [];
  const loader = createReferenceProfilesApi({ get: async (...args) => { calls.push(args); return { data: new ArrayBuffer(0) }; } });
  await assert.rejects(loader(), /identity differs/);
  assert.deepEqual(calls, [['/research/reference-profiles', { responseType: 'arraybuffer' }]]);
});

test('clinical registry remains empty and page never invokes normal result exports', async () => {
  const gate = await readFile(new URL('../src/lib/quantitative-gate.js', import.meta.url), 'utf8');
  const page = await readFile(new URL('../src/pages/ReferenceProfiles.jsx', import.meta.url), 'utf8');
  assert.match(gate, /Object\.freeze\(Object\.create\(null\)\)/);
  assert.doesNotMatch(page, /downloadRecords|reportJsonBlob|stenosis-results|percentage_narrowing/);
  assert.match(page, /REFERENCE_NOTICE/);
  assert.match(page, /spanGaps: false/);
});
