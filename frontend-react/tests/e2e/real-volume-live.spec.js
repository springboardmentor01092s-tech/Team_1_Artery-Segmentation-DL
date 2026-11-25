import {test, expect} from '@playwright/test';
import {readFile, writeFile} from 'node:fs/promises';
import path from 'node:path';

const apiOrigin = process.env.VASCUAI_REAL_VOLUME_API_URL;
const researchEmail = process.env.VASCUAI_REAL_VOLUME_RESEARCH_EMAIL;
const researchPassword = process.env.VASCUAI_REAL_VOLUME_RESEARCH_PASSWORD;
const clinicianEmail = process.env.VASCUAI_REAL_VOLUME_CLINICIAN_EMAIL;
const clinicianPassword = process.env.VASCUAI_REAL_VOLUME_CLINICIAN_PASSWORD;
const fixtureDir = process.env.VASCUAI_REAL_VOLUME_FIXTURE_DIR;
const responseMarker = process.env.VASCUAI_REAL_VOLUME_RESPONSE_MARKER;
const evidencePath = process.env.VASCUAI_REAL_VOLUME_EVIDENCE_PATH;

test('real-volume QC upload runs through React and the isolated authenticated FastAPI endpoint', async ({page, request}, testInfo) => {
  test.skip(!apiOrigin || !researchEmail || !researchPassword || !clinicianEmail || !clinicianPassword || !fixtureDir || !responseMarker || !evidencePath,
    'Requires explicitly provisioned disposable local API credentials and synthetic NIfTI fixtures');
  const api = apiOrigin.replace(/\/$/, '');
  const files = name => path.join(fixtureDir, name);

  // Log in through the real UI against the local FastAPI server.
  await page.goto('/login');
  await page.getByLabel('Email address').fill(researchEmail);
  await page.getByLabel('Password', {exact: true}).fill(researchPassword);
  await page.getByRole('button', {name: 'Sign in to workspace'}).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  await page.goto('/research/experimental-stenosis');
  await expect(page.getByRole('heading', {name: 'Real-volume research QC'})).toBeVisible();
  await page.getByLabel('CT volume (.nii or .nii.gz)').setInputFiles(files('ct-valid.nii'));
  await page.getByLabel('Matching binary vessel mask (.nii or .nii.gz)').setInputFiles(files('mask-valid.nii'));
  const actualUploadResponse = page.waitForResponse(response => response.url().includes('/api/v1/experimental-stenosis/real-volume/analyze'));
  await page.getByRole('button', {name: 'Validate and analyze pair'}).click();

  // No API route is fulfilled with synthetic test data: the response rendered
  // below is produced by FastAPI from these uploaded NIfTI files.
  await expect(page.getByRole('heading', {name: 'Ephemeral research result: profile_only'})).toBeVisible({timeout: 20000});
  const actualResponse = await actualUploadResponse;
  expect(actualResponse.status()).toBe(200);
  const actualBody = await actualResponse.json();
  expect(actualBody.provenance.persisted).toBe(false);
  expect(actualBody.provenance.synthetic_model_used).toBe(false);
  expect(actualBody.clinical_gate_authorized).toBe(false);
  expect(actualBody.training_release_authorized).toBe(false);
  const result = page.locator('[aria-labelledby="real-volume-research-title"]');
  await expect(result).toContainText(actualBody.geometry.shape_ijk.join(' × '));
  await expect(result).toContainText(actualBody.geometry.orientation.join(' / '));
  await expect(result).toContainText(actualBody.geometry.voxel_spacing_mm.join(' / '));
  await expect(result).toContainText(String(actualBody.segmentation.foreground_voxels));
  await expect(result).toContainText(String(actualBody.segmentation.component_count_26));
  await expect(result).toContainText('Connected components (26-neighbor)');
  await expect(result).toContainText('Candidate localization');
  await expect(result).toContainText('mask lumen semantics are not verified');
  await expect(result).toContainText('Percentage narrowing / provisional severity');
  await expect(result).toContainText('false / false');

  const apiStatuses = [{case: 'valid-ui-upload', status: actualResponse.status(), body: actualBody}];

  const researcherToken = await page.evaluate(() => localStorage.getItem('vascuai_token'));
  const auth = {Authorization: `Bearer ${researcherToken}`};
  const ct = await readFile(files('ct-valid.nii'));
  const mask = await readFile(files('mask-valid.nii'));
  const mismatch = await readFile(files('mask-dimensions-mismatch.nii'));
  const affineMismatch = await readFile(files('mask-affine-mismatch.nii'));
  const postPair = (ctBytes, ctName, maskBytes, maskName) => request.post(
    `${api}/api/v1/experimental-stenosis/real-volume/analyze`,
    {headers: auth, multipart: {
      ct_volume: {name: ctName, mimeType: 'application/octet-stream', buffer: ctBytes},
      vessel_mask: {name: maskName, mimeType: 'application/octet-stream', buffer: maskBytes},
    }},
  );

  const wrongExtension = await postPair(ct, 'ct.nii', mask, 'mask.dcm');
  expect(wrongExtension.status()).toBe(422);
  apiStatuses.push({case: 'unsupported-extension', status: wrongExtension.status()});
  const malformed = await postPair(Buffer.from('not a NIfTI'), 'ct.nii', mask, 'mask.nii');
  expect(malformed.status()).toBe(422);
  apiStatuses.push({case: 'malformed-nifti', status: malformed.status()});
  const dimensions = await postPair(ct, 'ct.nii', mismatch, 'mask.nii');
  expect(dimensions.status()).toBe(422);
  const dimensionBody = await dimensions.json();
  expect(dimensionBody.detail).toContain('dimensions_mismatch');
  apiStatuses.push({case: 'dimension-mismatch', status: dimensions.status(), detail: dimensionBody.detail});
  const affine = await postPair(ct, 'ct.nii', affineMismatch, 'mask.nii');
  expect(affine.status()).toBe(422);
  const affineBody = await affine.json();
  expect(affineBody.detail).toContain('affine_mismatch');
  apiStatuses.push({case: 'affine-mismatch', status: affine.status(), detail: affineBody.detail});

  // Verify endpoint RBAC using a distinct disposable Clinician account.
  const clinicianLogin = await request.post(`${api}/api/v1/auth/login`, {
    data: {email: clinicianEmail, password: clinicianPassword},
  });
  expect(clinicianLogin.status()).toBe(200);
  const clinicianToken = (await clinicianLogin.json()).access_token;
  const denied = await request.post(`${api}/api/v1/experimental-stenosis/real-volume/analyze`, {
    headers: {Authorization: `Bearer ${clinicianToken}`},
    multipart: {
      ct_volume: {name: 'ct.nii', mimeType: 'application/octet-stream', buffer: ct},
      vessel_mask: {name: 'mask.nii', mimeType: 'application/octet-stream', buffer: mask},
    },
  });
  expect(denied.status()).toBe(403);
  apiStatuses.push({case: 'unauthorized-role', status: denied.status()});
  const unauthenticated = await request.post(`${api}/api/v1/experimental-stenosis/real-volume/analyze`, {
    multipart: {
      ct_volume: {name: 'ct.nii', mimeType: 'application/octet-stream', buffer: ct},
      vessel_mask: {name: 'mask.nii', mimeType: 'application/octet-stream', buffer: mask},
    },
  });
  expect(unauthenticated.status()).toBe(401);
  apiStatuses.push({case: 'unauthenticated', status: unauthenticated.status()});

  // A test-only ASGI wrapper delays transmission after the real endpoint has
  // generated its complete response. No browser/API route is mocked.
  // Re-select fresh browser File objects for the independent in-flight session
  // invalidation check; the first upload has already verified the rendered result.
  await page.getByLabel('CT volume (.nii or .nii.gz)').setInputFiles(files('ct-valid.nii'));
  await page.getByLabel('Matching binary vessel mask (.nii or .nii.gz)').setInputFiles(files('mask-valid.nii'));
  await page.getByRole('button', {name: 'Validate and analyze pair'}).click();
  await expect.poll(async () => {
    try { return JSON.parse(await readFile(responseMarker, 'utf8')); } catch { return null; }
  }, {timeout: 20000}).toMatchObject({request_index: 2, status: 200, body_bytes: expect.any(Number)});
  await page.evaluate(() => window.dispatchEvent(new Event('vascuai:unauthorized')));
  await page.waitForTimeout(2500); // allow the actual buffered response to be transmitted
  await expect(page.getByRole('heading', {name: /Ephemeral research result/})).toHaveCount(0);
  apiStatuses.push({case: 'stale-real-api-response', status: 200, displayedAfterSessionChange: false});
  const ctInput = page.getByLabel('CT volume (.nii or .nii.gz)');
  const maskInput = page.getByLabel('Matching binary vessel mask (.nii or .nii.gz)');
  if (await ctInput.count()) expect(await ctInput.evaluate(input => input.files.length)).toBe(0);
  if (await maskInput.count()) expect(await maskInput.evaluate(input => input.files.length)).toBe(0);

  await testInfo.attach('real-volume-live-api-statuses.json', {
    body: JSON.stringify(apiStatuses, null, 2), contentType: 'application/json',
  });
  await writeFile(evidencePath, JSON.stringify(apiStatuses, null, 2), {encoding: 'utf8', flag: 'wx'});

  // Temporary upload-file cleanup is verified by the external test runner after
  // the actual API process exits, using its dedicated TMP/TEMP directory.
});
