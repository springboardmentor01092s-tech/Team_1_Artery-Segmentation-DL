// Synthetic browser tests must not inherit private .env files or proxy to a
// running development backend. Live integration remains a separate opt-in run.
import { createServer } from 'vite';
import { mkdtemp } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import config from '../../vite.config.js';

const address = new URL(process.env.PLAYWRIGHT_BASE_URL);
const artifacts = process.env.PLAYWRIGHT_ARTIFACT_DIR || await mkdtemp(path.join(tmpdir(), 'vascuai-browser-'));
let proxy;
if (process.env.PLAYWRIGHT_LIVE_API_URL) {
  const target = new URL(process.env.PLAYWRIGHT_LIVE_API_URL);
  if (target.protocol !== 'http:' || !['127.0.0.1', 'localhost'].includes(target.hostname)
      || target.username || target.password || target.pathname !== '/' || target.search || target.hash) {
    throw new Error('PLAYWRIGHT_LIVE_API_URL must be a credential-free HTTP loopback origin');
  }
  proxy = { '/api': { target: target.origin }, '/health': { target: target.origin } };
}
process.env.VITE_API_URL = '/api/v1';
process.env.VITE_HEALTH_URL = '/health';
const server = await createServer({
  ...config, configFile: false, envDir: artifacts,
  cacheDir: path.join(artifacts, 'vite-cache'),
  server: { host: address.hostname, port: Number(address.port || 80), strictPort: true, proxy },
});
await server.listen();
