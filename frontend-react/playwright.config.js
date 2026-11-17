import { defineConfig } from "@playwright/test";
import path from 'node:path';

const address = new URL(process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:5173');
if (address.protocol !== 'http:' || !['127.0.0.1', 'localhost'].includes(address.hostname)
    || address.username || address.password || address.pathname !== '/' || address.search || address.hash) {
  throw new Error('PLAYWRIGHT_BASE_URL must be a credential-free HTTP loopback origin');
}
process.env.PLAYWRIGHT_BASE_URL = address.origin;
const artifacts = process.env.PLAYWRIGHT_ARTIFACT_DIR;

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  workers: 2,
  timeout: 60_000,
  ...(artifacts ? { outputDir: path.join(artifacts, 'browser-results') } : {}),
  use: {
    baseURL: address.origin,
    viewport: { width: 1440, height: 1000 },
    reducedMotion: "reduce",
    screenshot: "only-on-failure",
    launchOptions: {
      executablePath:
        process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH || undefined,
    },
  },
  webServer: {
    command: "node tests/e2e/start-server.mjs",
    url: address.origin,
    reuseExistingServer: process.env.PLAYWRIGHT_REUSE_SERVER === '1',
  },
});
