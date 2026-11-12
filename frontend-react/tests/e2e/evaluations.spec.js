import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { installApi } from './fixtures';
import { evaluationFixture, indexFixture, runsFixture, sectionsFixture } from '../evaluation-fixtures';

async function installEvaluations(page, { conflict = false } = {}) {
  const { requests } = await installApi(page);
  const one = evaluationFixture(1), two = evaluationFixture(2);
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
