import { test, expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';

const apiOrigin = process.env.VASCUAI_LIVE_API_URL;
const expectedAvailable = process.env.VASCUAI_EXPECT_CHECKPOINT === '1';
const email = process.env.VASCUAI_LIVE_RESEARCH_EMAIL;
const password = process.env.VASCUAI_LIVE_RESEARCH_PASSWORD;
const clinicianEmail = process.env.VASCUAI_LIVE_CLINICIAN_EMAIL;
const clinicianPassword = process.env.VASCUAI_LIVE_CLINICIAN_PASSWORD;

test('real API synthetic workflow enforces auth, validation, checkpoint state and export', async ({ page, request }) => {
  test.skip(!apiOrigin || !email || !password || !clinicianEmail || !clinicianPassword,
    'Requires explicitly configured disposable local API credentials');
  const base = apiOrigin.replace(/\/$/, '');
  const clinicianLogin = await request.post(`${base}/api/v1/auth/login`, { data: { email: clinicianEmail, password: clinicianPassword } });
  expect(clinicianLogin.status()).toBe(200);
  const clinicianToken = (await clinicianLogin.json()).access_token;
  const denied = await request.get(`${base}/api/v1/experimental-stenosis/status`, { headers: { Authorization: `Bearer ${clinicianToken}` } });
  expect(denied.status()).toBe(403);

  const login = await request.post(`${base}/api/v1/auth/login`, { data: { email, password } });
  expect(login.status()).toBe(200);
  const token = (await login.json()).access_token;
  const headers = { Authorization: `Bearer ${token}` };
  const malformed = await request.post(`${base}/api/v1/experimental-stenosis/samples`, { headers, data: { sample_id: -1, synthetic_class_id: 2, seed: 1729 } });
  expect(malformed.status()).toBe(422);
  const patientLike = await request.post(`${base}/api/v1/experimental-stenosis/samples`, { headers, data: { sample_id: 1, synthetic_class_id: 2, seed: 1729, case_id: 1 } });
  expect(patientLike.status()).toBe(422);
  const sampleResponse = await request.post(`${base}/api/v1/experimental-stenosis/samples`, { headers, data: { sample_id: 2, synthetic_class_id: 1, seed: 1729 } });
  expect(sampleResponse.status()).toBe(200);
  const sampleBody = await sampleResponse.json();
  expect(sampleBody.schema_version).toBe('synthetic-stenosis-sample/0.2');
  expect(sampleBody).not.toHaveProperty('class_label');
  expect(JSON.stringify(sampleBody)).not.toContain('synthetic_geometry_ground_truth');
  const badThresholds = await request.post(`${base}/api/v1/experimental-stenosis/analyze`, { headers, data: {
    sample_id: 1, synthetic_class_id: 2, seed: 1729,
    provisional_severity_thresholds_percent: [10, 50, 30, 70],
  } });
  expect(badThresholds.status()).toBe(422);

  const init = token => localStorage.setItem('vascuai_token', token);
  await page.addInitScript(init, token);
  await page.goto('/research/experimental-stenosis');
  await expect(page.getByRole('heading', { name: 'Experimental Stenosis Analysis' })).toBeVisible();
  const status = await request.get(`${base}/api/v1/experimental-stenosis/status`, { headers });
  expect(status.status()).toBe(200);
  const state = await status.json();
  expect(state.clinical_gate_authorized).toBe(false);
  expect(state.training_release_authorized).toBe(false);
  expect(state.available).toBe(expectedAvailable);

  if (!expectedAvailable) {
    await expect(page.getByRole('status')).toContainText('unavailable');
    await page.getByRole('button', { name: 'Generate phantom' }).click();
    await expect(page.getByRole('heading', { name: 'Synthetic sample 1' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Run experimental analysis' })).toBeDisabled();
    return;
  }

  await page.getByRole('button', { name: 'Generate phantom' }).click();
  await expect(page.getByRole('heading', { name: 'Synthetic sample 1' })).toBeVisible();
  await page.getByRole('button', { name: 'Run experimental analysis' }).click();
  await expect(page.getByRole('heading', { name: 'Experimental result' })).toBeVisible({ timeout: 30000 });
  await expect(page.getByRole('heading', { name: 'Experimental geometry measurements' })).toBeVisible();
  await expect(page.getByText('Measurement confidence / uncertainty')).toBeVisible();
  await expect(page.getByRole('img', { name: 'Synthetic-only model Grad-CAM central slice' })).toBeVisible();
  await expect(page.getByText('false / false', { exact: true })).toBeVisible();
  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Export research JSON' }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe('vascuai-synthetic-stenosis-1.json');
  const exported = JSON.parse(await readFile(await download.path(), 'utf8'));
  expect(exported.clinical_gate_authorized).toBe(false);
  expect(exported.training_release_authorized).toBe(false);
  expect(exported.provenance.patient_case_id).toBeNull();
  expect(exported.explainability.scope).toBe('synthetic_generated_phantom_only');
  expect(exported.geometry_analysis.measurement_provenance.input_volume_sha256).toBe(exported.provenance.volume_sha256);
  expect(exported.geometry_analysis.measurement_provenance.provisional_severity_thresholds_percent).toEqual([10, 30, 50, 70]);
  expect(exported.geometry_analysis.metrics.measurement_confidence).toBeNull();
  expect(exported.geometry_analysis.metrics.measurement_uncertainty).toBeNull();
});
