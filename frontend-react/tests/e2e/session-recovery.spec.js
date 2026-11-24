import { test, expect } from '@playwright/test';
import { installApi } from './fixtures';

const identity = { id: 1, full_name: 'Verified user', role: 'Admin', is_active: true };
async function seed(page) {
  const fixture = await installApi(page, { authenticated: false });
  await page.addInitScript(() => {
    if (!sessionStorage.getItem('seeded')) {
      localStorage.setItem('vascuai_token', 'restoration-test-token');
      localStorage.setItem('vascuai_user', JSON.stringify({ role: 'Admin', full_name: 'Forged cache' }));
      sessionStorage.setItem('seeded', '1');
    }
  });
  return fixture;
}
for (const failure of ['503', 'network']) test(`temporary ${failure} retains token, blocks protected reads and retries`, async ({ page }) => {
  const fixture = await seed(page);
  let unavailable = true;
  await page.route('**/api/v1/auth/me', (route) => unavailable
    ? failure === 'network' ? route.abort('connectionfailed') : route.fulfill({ status: 503, json: { detail: 'Temporarily unavailable' } })
    : route.fulfill({ json: identity }));
  await page.goto('/cases?review=1');
  await expect(page.getByRole('heading', { name: 'Session verification unavailable' })).toBeVisible();
  expect(await page.evaluate(() => localStorage.getItem('vascuai_token'))).toBe('restoration-test-token');
  expect(fixture.requests.filter((r) => r.path === '/cases')).toHaveLength(0);
  await expect(page.getByText('Forged cache')).toHaveCount(0);
  unavailable = false;
  await page.getByRole('button', { name: 'Retry', exact: true }).click();
  await expect(page.getByText('CASE-001', { exact: true })).toBeVisible();
  await expect(page).toHaveURL(/\/cases\?review=1$/);
  await page.reload();
  await expect(page.getByText('CASE-001', { exact: true })).toBeVisible();
});
test('invalid credentials clear token and permit login without trusting cached identity', async ({ page }) => {
  await seed(page);
  await page.route('**/api/v1/auth/me', (route) => route.fulfill({ status: 401, json: { detail: 'Expired' } }));
  await page.goto('/cases'); await expect(page).toHaveURL(/\/login$/);
  expect(await page.evaluate(() => localStorage.getItem('vascuai_token'))).toBeNull();
  await page.getByLabel('Email address').fill('synthetic@example.test');
  await page.getByLabel('Password', { exact: true }).fill('synthetic-test-password');
  await page.getByRole('button', { name: 'Sign in to workspace', exact: true }).click();
  await expect(page.getByText('CASE-001', { exact: true })).toBeVisible();
});
test('malformed session response cannot authorize protected content', async ({ page }) => {
  const fixture = await seed(page);
  await page.route('**/api/v1/auth/me', (route) => route.fulfill({ json: { role: 'Admin' } }));
  await page.goto('/cases');
  await expect(page.getByRole('heading', { name: 'Session verification unavailable' })).toBeVisible();
  expect(fixture.requests.filter((r) => r.path === '/cases')).toHaveLength(0);
  await page.getByRole('button', { name: 'Sign out on this device' }).click();
  await expect(page).toHaveURL(/\/login$/);
  expect(await page.evaluate(() => localStorage.getItem('vascuai_token'))).toBeNull();
});
test('cross-tab logout invalidates an outstanding restoration response', async ({ page }) => {
  const fixture = await seed(page);
  let release; const blocked = new Promise((resolve) => { release = resolve; });
  let requested; const started = new Promise((resolve) => { requested = resolve; });
  await page.route('**/api/v1/auth/me', async (route) => {
    requested(); await blocked; await route.fulfill({ json: identity }).catch(() => {});
  });
  await page.goto('/cases'); await started;
  await page.evaluate(() => {
    localStorage.removeItem('vascuai_token');
    window.dispatchEvent(new StorageEvent('storage', { key: 'vascuai_token', newValue: null }));
  });
  await expect(page).toHaveURL(/\/login$/); release();
  await expect(page.getByRole('button', { name: 'Sign in to workspace', exact: true })).toBeVisible();
  expect(fixture.requests.filter((r) => r.path === '/cases')).toHaveLength(0);
});
test('logout revokes the server session and clears local credentials', async ({ page }) => {
  const fixture = await seed(page); await page.goto('/cases');
  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  await expect(page).toHaveURL(/\/login$/);
  expect(fixture.requests.some((r) => r.path === '/auth/logout' && r.method === 'POST')).toBe(true);
  expect(await page.evaluate(() => localStorage.getItem('vascuai_token'))).toBeNull();
});

test('a delayed logout cannot destroy a newly verified session', async ({ page }) => {
  await seed(page); await page.goto('/cases');
  let release; const blocked = new Promise((resolve) => { release = resolve; });
  let requested; const started = new Promise((resolve) => { requested = resolve; });
  await page.route('**/api/v1/auth/logout', async (route) => { requested(); await blocked; await route.fulfill({ json: { message: 'Signed out' } }); });
  await page.getByRole('button', { name: 'Sign out', exact: true }).click(); await started;
  await page.route('**/api/v1/auth/me', (route) => route.fulfill({ json: { ...identity, id: 2, full_name: 'New verified session' } }));
  await page.evaluate(() => {
    localStorage.setItem('vascuai_token', 'new-session-test-token');
    window.dispatchEvent(new StorageEvent('storage', { key: 'vascuai_token' }));
  });
  await expect(page.getByText('New verified session', { exact: true })).toBeVisible();
  const finished = page.waitForResponse((response) => response.url().endsWith('/auth/logout'));
  release(); await (await finished).finished();
  await page.getByRole('link', { name: 'Cases', exact: true }).click();
  await expect(page.getByText('New verified session', { exact: true })).toBeVisible();
  await expect(page.getByText('CASE-001', { exact: true })).toBeVisible();
  expect(await page.evaluate(() => localStorage.getItem('vascuai_token'))).toBe('new-session-test-token');
});

for (const operation of ['profile', 'password']) test(`late ${operation} update cannot restore a previous identity`, async ({ page }) => {
  await seed(page); await page.goto(operation === 'password' ? '/profile?tab=password' : '/profile');
  let release; const blocked = new Promise((resolve) => { release = resolve; });
  let requested; const started = new Promise((resolve) => { requested = resolve; });
  const path = operation === 'password' ? '/auth/password' : '/auth/me';
  await page.route(`**/api/v1${path}`, async (route) => {
    if (route.request().method() === 'GET') return route.fulfill({ json: { ...identity, id: 2, full_name: 'New verified session' } });
    requested(); await blocked;
    const oldUser = { ...identity, full_name: 'Late old identity' };
    await route.fulfill({ json: operation === 'password' ? { access_token: 'late-old-token', user: oldUser } : oldUser });
  });
  if (operation === 'profile') {
    await page.locator('#profile-name').fill('Changed synthetic name');
    await page.getByRole('button', { name: 'Save changes', exact: true }).click();
  } else {
    await page.locator('#current-pw').fill('synthetic-old-password');
    await page.locator('#new-pw').fill('synthetic-new-password');
    await page.locator('#confirm-pw').fill('synthetic-new-password');
    await page.getByRole('button', { name: 'Update password', exact: true }).click();
    await page.route('**/api/v1/auth/me', (route) => route.fulfill({ json: { ...identity, id: 2, full_name: 'New verified session' } }));
  }
  await started;
  await page.evaluate(() => {
    localStorage.setItem('vascuai_token', 'new-session-test-token');
    window.dispatchEvent(new StorageEvent('storage', { key: 'vascuai_token' }));
  });
  await expect(page.getByRole('complementary', { name: 'Workspace navigation' }).getByText('New verified session', { exact: true })).toBeVisible();
  const finished = page.waitForResponse((response) => response.url().endsWith(path) && response.request().method() !== 'GET');
  release(); await (await finished).finished();
  await page.getByRole('link', { name: 'Cases', exact: true }).click();
  await expect(page.getByText('CASE-001', { exact: true })).toBeVisible();
  await expect(page.getByRole('complementary', { name: 'Workspace navigation' }).getByText('New verified session', { exact: true })).toBeVisible();
  await expect(page.getByText('Late old identity', { exact: true })).toHaveCount(0);
  expect(await page.evaluate(() => localStorage.getItem('vascuai_token'))).toBe('new-session-test-token');
});

for (const operation of ['login', 'registration']) test(`late ${operation} response cannot replace another verified session`, async ({ page }) => {
  await installApi(page, { authenticated: false });
  await page.goto(operation === 'login' ? '/login' : '/register');
  let release; const blocked = new Promise((resolve) => { release = resolve; });
  let requested; const started = new Promise((resolve) => { requested = resolve; });
  await page.route('**/api/v1/auth/login', async (route) => { requested(); await blocked;
    await route.fulfill({ json: { access_token: 'late-login-token', user: { ...identity, full_name: 'Late login identity' } } });
  });
  await page.route('**/api/v1/auth/me', (route) => route.fulfill({ json: { ...identity, id: 2, full_name: 'New verified session' } }));
  if (operation === 'registration') {
    await page.getByLabel('Full name', { exact: true }).fill('Synthetic registration');
  }
  await page.getByLabel('Email address', { exact: true }).fill('synthetic@example.test');
  await page.getByLabel('Password', { exact: true }).fill('synthetic-test-password-123');
  if (operation === 'registration') {
    await page.getByLabel('Confirm password', { exact: true }).fill('synthetic-test-password-123');
    await page.getByRole('checkbox').check();
  }
  await page.getByRole('button', { name: operation === 'login' ? 'Sign in to workspace' : 'Create account', exact: true }).click();
  await started;
  await page.evaluate(() => {
    localStorage.setItem('vascuai_token', 'new-session-test-token');
    window.dispatchEvent(new StorageEvent('storage', { key: 'vascuai_token' }));
  });
  await expect(page.getByRole('complementary', { name: 'Workspace navigation' }).getByText('New verified session', { exact: true })).toBeVisible();
  const finished = page.waitForResponse((response) => response.url().endsWith('/auth/login'));
  release(); await (await finished).finished();
  await page.getByRole('link', { name: 'Cases', exact: true }).click();
  await expect(page.getByText('CASE-001', { exact: true })).toBeVisible();
  await expect(page.getByText('Late login identity', { exact: true })).toHaveCount(0);
  expect(await page.evaluate(() => localStorage.getItem('vascuai_token'))).toBe('new-session-test-token');
});
