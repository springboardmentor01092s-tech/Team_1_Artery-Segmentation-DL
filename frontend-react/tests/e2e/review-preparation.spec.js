// Isolated browser contracts, never a live patient/application-database demo.
// All identities, volumes and returned records below are synthetic test fixtures.
import { test, expect } from '@playwright/test';
import { createHash } from 'node:crypto';
import { gzipSync } from 'node:zlib';
import { installApi } from './fixtures';
import { syntheticNifti } from './nifti-fixture';
import { geometryFixture, resultFixture } from '../stenosis-results-fixtures';
import { reportFixture } from '../reporting-fixtures';

test('case to saved segmentation viewer to disabled stenosis/history and analytics', async ({ page }) => {
  await installApi(page, { role: 'Clinician' });
  const geometry = structuredClone(geometryFixture);
  const ct = gzipSync(syntheticNifti({ affine: geometry.affine }));
  const mask = gzipSync(syntheticNifti({ affine: geometry.affine, mask: true }));
  const root = await resultFixture({ geometry, sourceHash: createHash('sha256').update(ct).digest('hex'), count: 0 });
  await page.route('**/api/v1/cases/1/segmentations**', route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith('/segmentations')) return route.fulfill({ json: [root.segmentation] });
    return route.fulfill({ contentType: 'application/gzip', body: path.endsWith('/source') ? ct : mask });
  });
  await page.goto('/cases/1');
  await page.getByRole('link', { name: 'Segmentation', exact: true }).click();
  await page.getByRole('button', { name: `View CT + Segmentation for run ${root.segmentation.id}` }).click();
  await expect(page.getByText(/Voxel spacing \(original axes\):/)).toBeVisible({ timeout: 30_000 });
  await page.getByRole('button', { name: 'Close viewer', exact: true }).click();
  await page.getByRole('link', { name: 'Stenosis', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Start stenosis analysis', exact: true })).toBeDisabled();
  await expect(page.getByText('Stenosis analysis is not operational', { exact: false })).toBeVisible();
  await expect(page.getByText('Stenosis analysis history', { exact: true })).toBeVisible();
  await page.getByRole('link', { name: 'Case analytics and research reports', exact: true }).click();
  await expect(page.getByText('No analysis selected.', { exact: false })).toBeVisible();
  await expect(page.getByText('Severity analytics unavailable:', { exact: false })).toBeVisible();
  await expect(page.getByText('Measurement summaries unavailable:', { exact: false })).toBeVisible();
});

test('unvalidated numeric report is withheld before display or export controls', async ({ page }) => {
  await installApi(page, { role: 'Researcher' });
  const report = await reportFixture({ count: 1 });
  report.result.result.lesions[0].measurements.percentage_narrowing = {
    value: 25, unit: 'percent', unavailable_reason: null, method_id: 'synthetic-test-only',
    method_version: 'v1', definition: 'Negative bypass fixture, not a real finding',
    validation_gate: { gate_id: 'synthetic-unregistered', validated: true },
  };
  await page.route('**/api/v1/cases/1/stenosis/analyses/*/report', route => route.fulfill({ json: report }));
  await page.goto(`/cases/1/stenosis/report/${report.analysis.analysis_id}`);
  await expect(page.getByRole('alert')).toContainText('No validated quantitative stenosis gate');
  await expect(page.getByText('25 percent', { exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Download report JSON', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Download findings CSV', exact: true })).toHaveCount(0);
});
