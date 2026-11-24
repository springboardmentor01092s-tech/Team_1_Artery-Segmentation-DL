import { test, expect } from '@playwright/test';
import { installApi } from './fixtures';

test('public workflow distinguishes saved-output viewing from new inference', async ({ page }) => {
  await installApi(page, { authenticated: false });
  await page.goto('/');
  await expect(page.getByText('Review input readiness. Interactive 3D viewing uses saved segmentation outputs; new inference requires a configured runtime.', { exact: true })).toBeVisible();
  await expect(page.getByText('Experimental research visualization — not for diagnostic use.', { exact: false })).toBeVisible();
});

test('pending access save prevents conflicting edits and deactivation', async ({ page }) => {
  await installApi(page);
  const target = { id: 2, full_name: 'Synthetic Researcher', email: 'researcher@example.test',
    role: 'Researcher', is_active: true };
  await page.route('**/api/v1/admin/users?*', route => route.fulfill({ json: [target] }));
  let release;
  const pending = new Promise(resolve => { release = resolve; });
  await page.route('**/api/v1/admin/users/2', async route => {
    await pending;
    await route.fulfill({ json: { ...target, ...route.request().postDataJSON() } });
  });
  try {
    await page.goto('/admin/users');
    await page.locator('#edit-role-2-btn').click();
    const selector = page.getByLabel('Role for Synthetic Researcher', { exact: true });
    await selector.selectOption('DataScientist');
    await page.getByRole('button', { name: 'Save', exact: true }).click();
    await expect(page.locator('#deactivate-2-btn')).toBeDisabled();
    await expect(selector).toBeDisabled();
    await expect(page.getByRole('button', { name: 'Cancel role change', exact: true })).toBeDisabled();
    release();
    await expect(page.locator('#deactivate-2-btn')).toBeEnabled();
    await page.locator('#deactivate-2-btn').click();
    await expect(page.getByText('Deactivate user?', { exact: true })).toBeVisible();
    await expect(page.locator('#confirm-deactivate-btn')).toBeEnabled();
    await page.getByRole('button', { name: 'Cancel', exact: true }).click();
    await expect(page.getByText('Deactivate user?', { exact: true })).toBeHidden();
  } finally {
    release();
  }
});
