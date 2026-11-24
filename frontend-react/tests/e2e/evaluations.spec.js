import { test, expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import AxeBuilder from '@axe-core/playwright';
import { installApi } from './fixtures';
import { evaluationFixture, indexFixture, runsFixture, sectionsFixture, supplementalFixture } from '../evaluation-fixtures';

async function installEvaluations(page, { conflict = false, role = 'Admin', additional = false } = {}) {
  const { requests } = await installApi(page, { role });
  const one = evaluationFixture(1), two = evaluationFixture(2);
  if (additional) for (const record of [one, two]) {
    record.summary.supplemental_metrics = supplementalFixture();
    record.cases.supplemental_metrics = supplementalFixture();
  }
  await page.route('**/api/v1/evaluations**', (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    if (path.endsWith('/compare')) return conflict
      ? route.fulfill({ status: 409, json: { detail: 'Evaluations cannot be compared: case sets must match exactly' } })
      : route.fulfill({ json: { case_ids: [1,2], evaluations: [one.summary,two.summary], metric_definitions_match: false, reference_artifacts_match: true, exclusions_match: true } });
    const record = path.includes(two.identity.id) ? two : one;
    return route.fulfill({ json: path.endsWith('/summary') ? record.summary : path.endsWith('/cases') ? record.cases : indexFixture([one.identity,two.identity]) });
  });
  await page.route('**/api/v1/models/**/runs*', (route) => route.fulfill({ json: runsFixture(one.identity) }));
  await page.route('**/api/v1/stenosis/evaluations/**/cases/*/sections', (route) => route.fulfill({ json: sectionsFixture(one.identity.id) }));
  return { one, two, requests };
}
test('supplemental statistics keep zero, missing TN, exclusions and surface-distance unavailability visible', async ({ page }) => {
  const { one } = await installEvaluations(page, { additional: true });
  await page.goto('/evaluation');
  await page.getByLabel('Evaluation record').selectOption(one.identity.id);
  const table = page.getByRole('table').filter({ has: page.getByText('Count-derived segmentation statistics (0–1)', { exact: true }) });
  await expect(table.getByRole('cell', { name: '0.000000', exact: true })).toHaveCount(6);
  await expect(table.getByRole('cell', { name: 'Unavailable', exact: true })).toHaveCount(2);
  await expect(page.getByText('Hausdorff distance / average surface distance: unavailable.', { exact: false })).toBeVisible();
  await page.getByText('Case 2 artifact provenance', { exact: true }).click();
  await expect(page.getByText('confusion_counts_unavailable', { exact: false }).first()).toBeVisible();
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download evaluation JSON', exact: true }).click();
  const exported = JSON.parse(await readFile(await (await download).path(), 'utf8'));
  expect(exported.summary.supplemental_metrics.macro_metrics.voxel_accuracy).toBe(0);
  expect(exported.summary.supplemental_metrics.surface_distances.hausdorff_distance).toBeNull();
});
for (const role of ['Admin', 'DataScientist']) test(`${role} uploads actual multipart JSON then imports its real returned artifact ID`, async ({ page }) => {
  const { one } = await installEvaluations(page, { role });
  const payload = Buffer.from(JSON.stringify({ schema_version: 'offline-evaluation/1.0', metadata: one.identity.metadata, cases: one.cases.cases }));
  let uploads = 0, imports = 0;
  await page.route('**/api/v1/evaluations/artifacts', route => {
    uploads++;
    expect(route.request().headers()['content-type']).toMatch(/^multipart\/form-data; boundary=/);
    expect(route.request().postData()).toContain(payload.toString());
    return route.fulfill({ status: 201, json: { id: one.identity.source_artifact_id, sha256: createHash('sha256').update(payload).digest('hex'),
      size_bytes: payload.length, schema_version: 'offline-evaluation/1.0', created_at: one.identity.created_at } });
  });
  await page.route('**/api/v1/evaluations/import', route => {
    imports++;
    expect(route.request().postDataJSON()).toEqual({ source_artifact_id: one.identity.source_artifact_id, metadata: one.identity.metadata });
    return route.fulfill({ status: imports === 1 ? 503 : 200, json: imports === 1 ? { detail: 'Synthetic response lost after import' } : one.summary });
  });
  await page.goto('/evaluation');
  await page.getByLabel('Offline evaluation JSON').setInputFiles({ name: 'synthetic.json', mimeType: 'application/json', buffer: payload });
  await page.getByRole('button', { name: 'Upload evaluation artifact', exact: true }).click();
  await expect(page.getByText('Artifact stored and verified:', { exact: false })).toBeVisible();
  expect(uploads).toBe(1); expect(imports).toBe(0);
  await page.getByRole('button', { name: 'Import stored evaluation', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Retry uses this same stored artifact ID');
  expect(imports).toBe(1);
  await page.getByRole('button', { name: 'Import stored evaluation', exact: true }).click();
  await expect(page.getByText('Evaluation imported.', { exact: false })).toBeVisible();
  expect(uploads).toBe(1); expect(imports).toBe(2);
});

test('read-only researcher has no import controls', async ({ page }) => {
  await installEvaluations(page, { role: 'Researcher' });
  await page.goto('/evaluation');
  await expect(page.getByRole('heading', { name: 'Accessible imported evaluations' })).toBeVisible();
  await expect(page.getByLabel('Offline evaluation JSON')).toHaveCount(0);
});

test('invalid JSON produces an actionable error without uploading or importing', async ({ page }) => {
  await installEvaluations(page);
  let writes = 0;
  await page.route('**/api/v1/evaluations/artifacts', route => { writes++; return route.abort(); });
  await page.goto('/evaluation');
  await page.getByLabel('Offline evaluation JSON').setInputFiles({ name: 'broken.json', mimeType: 'application/json', buffer: Buffer.from('{broken') });
  await page.getByRole('button', { name: 'Upload evaluation artifact', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('No upload was sent');
  expect(writes).toBe(0);
  await expect(page.getByRole('button', { name: 'Import stored evaluation', exact: true })).toHaveCount(0);
});
test('evaluation downloads contain the recorded evidence and print invokes the browser PDF workflow', async ({ page }, testInfo) => {
  await page.addInitScript(() => { window.print = () => { document.documentElement.dataset.printCalls = '1'; }; });
  const { one } = await installEvaluations(page);
  await page.goto('/evaluation');
  await page.getByLabel('Evaluation record').selectOption(one.identity.id);
  const jsonDownload = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download evaluation JSON', exact: true }).click();
  const json = await jsonDownload;
  expect(json.suggestedFilename()).toBe(`vascuai-evaluation-${one.identity.id}.json`);
  const report = JSON.parse(await readFile(await json.path(), 'utf8'));
  expect(report.summary.macro_metrics.dice).toBe(0);
  expect(report.summary.macro_metrics.precision).toBeNull();
  expect(report.cases.cases[1].exclusion_reason).toBe('Synthetic exclusion');
  expect(report.quantitative_stenosis_available).toBe(false);
  const csvDownload = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download evaluation CSV', exact: true }).click();
  const csv = await csvDownload;
  const content = await readFile(await csv.path(), 'utf8');
  expect(content).toContain('macro_headline'); expect(content).toContain('case_excluded');
  expect(content).toContain(one.summary.checkpoint_sha256);
  await page.getByRole('button', { name: 'Print / Save evaluation PDF', exact: true }).click();
  await expect(page.locator('html')).toHaveAttribute('data-print-calls', '1');
  await page.emulateMedia({ media: 'print' });
  await expect(page.getByText('Research segmentation evidence only.', { exact: false })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Download evaluation JSON', exact: true })).toBeHidden();
  const pdf = await page.pdf({ path: testInfo.outputPath('synthetic-evaluation-report.pdf'), format: 'A4', printBackground: true });
  expect(pdf.subarray(0, 5).toString()).toBe('%PDF-');
});
test('empty evaluations are honest and refresh recovers an API failure', async ({ page }) => {
  await installApi(page); let fail = true;
  await page.route('**/api/v1/evaluations?*', (route) => route.fulfill(fail
    ? { status: 503, json: { detail: 'Evaluation storage temporarily unavailable' } } : { json: indexFixture() }));
  await page.goto('/evaluation');
  await expect(page.getByRole('alert')).toContainText('Evaluation storage temporarily unavailable');
  await expect(page.getByText('No evaluations imported yet')).toHaveCount(0);
  fail = false; await page.getByRole('button', { name: 'Retry', exact: true }).click();
  await expect(page.getByText('No evaluations imported yet')).toBeVisible();
});
test('real response records show macro, nulls, exclusions, history and unavailable stenosis', async ({ page }) => {
  const { one, requests } = await installEvaluations(page);
  await page.goto('/evaluation'); await page.getByLabel('Evaluation record').selectOption(one.identity.id);
  await expect(page.getByRole('heading', { name: 'Case-wise segmentation results' })).toBeVisible();
  await expect(page.getByText('Macro-average (headline)', { exact: true })).toBeVisible();
  await expect(page.getByRole('cell', { name: '0.000000', exact: true }).first()).toBeVisible();
  await expect(page.getByRole('cell', { name: 'Unavailable', exact: true }).first()).toBeVisible();
  await expect(page.getByText('Synthetic exclusion', { exact: false }).first()).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Imported model run history' })).toBeVisible();
  await page.getByText('Case 1 artifact provenance', { exact: true }).click();
  await page.getByRole('button', { name: 'View stenosis availability for case 1', exact: true }).click();
  await expect(page.getByText('Stenosis measurement unavailable', { exact: true })).toBeVisible();
  await expect(page.getByText('reference_annotation', { exact: true })).toBeVisible();
  expect(requests.filter((r) => r.method !== 'GET')).toHaveLength(0);
  const violations = (await new AxeBuilder({ page }).withTags(['wcag2a','wcag2aa']).analyze()).violations;
  expect(violations).toEqual([]);
});
test('comparison reports differing protocols without ranking models', async ({ page }) => {
  const errors = [];
  page.on('console', (message) => { if (message.type() === 'error') errors.push(message.text()); });
  await installEvaluations(page); await page.goto('/models/compare');
  await page.getByRole('checkbox').nth(0).check(); await page.getByRole('checkbox').nth(1).check();
  await page.getByRole('button', { name: 'Compare 2 evaluations' }).click();
  await expect(page.getByText('Protocols differ.', { exact: false })).toBeVisible();
  await expect(page.getByText('No model winner is inferred.', { exact: false })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Recorded evaluation comparison' })).toBeVisible();
  expect(errors).toEqual([]);
});
test('different case sets keep the API conflict visible', async ({ page }) => {
  await installEvaluations(page, { conflict: true }); await page.goto('/models/compare');
  await page.getByRole('checkbox').nth(0).check(); await page.getByRole('checkbox').nth(1).check();
  await page.getByRole('button', { name: 'Compare 2 evaluations' }).click();
  await expect(page.getByRole('alert')).toContainText('case sets must match exactly');
  await expect(page.getByRole('heading', { name: 'Recorded evaluation comparison' })).toHaveCount(0);
});
test('evaluation screen remains usable on narrow viewports', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 }); const { one } = await installEvaluations(page);
  await page.goto('/evaluation'); await page.getByLabel('Evaluation record').selectOption(one.identity.id);
  await expect(page.getByRole('heading', { name: 'Case-wise segmentation results' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test('refreshing discovery clears stale comparison evidence even if the refresh fails', async ({ page }) => {
  await installEvaluations(page); await page.goto('/models/compare');
  await page.getByRole('checkbox').nth(0).check(); await page.getByRole('checkbox').nth(1).check();
  await page.getByRole('button', { name: 'Compare 2 evaluations' }).click();
  await expect(page.getByRole('heading', { name: 'Recorded evaluation comparison' })).toBeVisible();
  await page.route('**/api/v1/evaluations?*', (route) => route.fulfill({ status: 503, json: { detail: 'Synthetic storage unavailable' } }));
  await page.getByRole('button', { name: 'Refresh list' }).click();
  await expect(page.getByRole('alert')).toContainText('Synthetic storage unavailable');
  await expect(page.getByRole('heading', { name: 'Recorded evaluation comparison' })).toHaveCount(0);
});
