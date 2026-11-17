import { test, expect } from '@playwright/test';
import { installApi } from './fixtures';

test('reference display rejects forged numeric evidence before plotting', async ({ page }) => {
  await installApi(page, { role: 'Researcher' });
  await page.route('**/api/v1/research/reference-profiles', route => route.fulfill({ json: {
    validated: true, gate_id: 'reference-profile/0.1', sections: [{ diameter_mm: 37 }],
  } }));
  await page.goto('/research/reference-profiles');
  await expect(page.getByRole('note')).toContainText('reference-derived research measurement, not validated');
  await expect(page.getByRole('alert')).toContainText('artifact identity differs');
  await expect(page.locator('canvas')).toHaveCount(0);
  await page.emulateMedia({ media: 'print' });
  await expect(page.getByRole('note')).toBeVisible();
  await expect(page.getByRole('note')).toContainText('reference-derived research measurement, not validated');
});

test('reference display missing pack remains an explicit unavailable state', async ({ page }) => {
  await installApi(page, { role: 'DataScientist' });
  await page.route('**/api/v1/research/reference-profiles', route => route.fulfill({ status: 503, json: { detail: 'unavailable' } }));
  await page.goto('/research/reference-profiles');
  await expect(page.getByRole('alert')).toContainText('Approved reference profile evidence unavailable');
  await expect(page.locator('canvas')).toHaveCount(0);
});

test('clinical-only role cannot enter the separate reference research display', async ({ page }) => {
  await installApi(page, { role: 'Clinician' });
  await page.route('**/api/v1/research/reference-profiles', () => { throw new Error('Denied role must not request reference evidence'); });
  await page.goto('/research/reference-profiles');
  await expect(page.getByRole('heading', { name: 'This area needs different access.' })).toBeVisible();
});
