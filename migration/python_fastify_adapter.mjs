// Migration-only transport adapter: runs the unchanged legacy HTTP assertions on FastAPI.
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync } from 'node:fs';
import net from 'node:net';
import { join } from 'node:path';

export const SESSION_COOKIE_NAME = 'tournament_admin_session';

export async function createApp(options) {
  const temporary = mkdtempSync(join(process.env.TOURNAMENT_WORK, 'api-'));
  const socket = net.createServer();
  await new Promise(resolve => socket.listen(0, '127.0.0.1', resolve));
  const port = socket.address().port;
  await new Promise(resolve => socket.close(resolve));
  const processHandle = spawn(process.env.TOURNAMENT_PYTHON, [
    '-m', 'uvicorn', 'app.main:create_app', '--factory', '--host', '127.0.0.1',
    '--port', String(port), '--no-proxy-headers',
  ], { cwd: process.env.TOURNAMENT_BACKEND, env: {
    ...process.env, ADMIN_PASSWORD: options.authentication.adminPassword,
    SESSION_SECRET: options.authentication.sessionSecret,
    DATABASE_PATH: join(temporary, 'tournament.sqlite'), APP_BASE_PATH: options.basePath,
    TRUST_PROXY: 'false', PYTHONDONTWRITEBYTECODE: '1',
  }, stdio: ['ignore', 'pipe', 'pipe'] });
  let logs = '';
  processHandle.stdout.on('data', chunk => { logs += chunk; });
  processHandle.stderr.on('data', chunk => { logs += chunk; });
  const base = `http://127.0.0.1:${port}`;
  async function close() {
    if (processHandle.exitCode === null) {
      processHandle.kill('SIGTERM');
      const timer = setTimeout(() => processHandle.kill('SIGKILL'), 3000);
      await new Promise(resolve => processHandle.once('exit', resolve));
      clearTimeout(timer);
    }
    rmSync(temporary, { recursive: true, force: true });
  }
  try {
    let ready = false;
    for (let count = 0; count < 100; count++) {
      try {
        const response = await fetch(base + '/api/auth/session');
        if (response.ok) { ready = true; break; }
      } catch { /* Wait for Uvicorn to bind its socket. */ }
      if (processHandle.exitCode !== null) throw new Error(logs);
      await new Promise(resolve => setTimeout(resolve, 50));
    }
    if (!ready) throw new Error('FastAPI startup timed out: ' + logs);
  } catch (error) {
    await close();
    throw error;
  }
  return {
    ready: async () => {}, listen: async () => {}, server: { address: () => ({ port }) }, close,
    async inject(input) {
      const headers = { ...input.headers };
      if (input.payload !== undefined) headers['content-type'] = 'application/json';
      const response = await fetch(base + input.url, {
        method: input.method, headers,
        body: input.payload === undefined ? undefined : JSON.stringify(input.payload),
      });
      const body = await response.text();
      return {
        statusCode: response.status, headers: Object.fromEntries(response.headers), body,
        json: () => JSON.parse(body),
        cookies: response.headers.getSetCookie().map(cookie => {
          const [pair] = cookie.split(';');
          const separator = pair.indexOf('=');
          return { name: pair.slice(0, separator), value: pair.slice(separator + 1) };
        }),
      };
    },
  };
}
