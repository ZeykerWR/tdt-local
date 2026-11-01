// The Python server of TDT local, started and stopped by the desktop app. Nothing here needs Electron.
import { spawn } from 'node:child_process';
import { createServer } from 'node:net';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

export const REPO_ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');

/** A port that is free right now on this machine. */
export function freePort() {
  return new Promise((resolve, reject) => {
    const probe = createServer();
    probe.once('error', reject);
    probe.listen(0, '127.0.0.1', () => {
      const { port } = probe.address();
      probe.close(() => resolve(port));
    });
  });
}

/**
 * How to start the server. Installed: the frozen server that travels in `resources/server/`. In development: `python -m
 * tdtlocal` from the repository, or the frozen one from `TDT_SERVER_EXE` (to try the installed path without installing).
 */
export function serverCommandFor({ packaged, resourcesPath, repoRoot, dataDir, env = process.env, platform = process.platform }) {
  const exeName = platform === 'win32' ? 'tdt-local-server.exe' : 'tdt-local-server';
  const frozen = env.TDT_SERVER_EXE || (packaged ? join(resourcesPath, 'server', exeName) : '');
  const common = { env: { TDT_DATA_DIR: dataDir } };
  if (frozen) return { file: frozen, args: [], cwd: dirname(frozen), ...common };
  return { file: env.TDT_PYTHON || (platform === 'win32' ? 'python' : 'python3'), args: ['-m', 'tdtlocal'], cwd: repoRoot, ...common };
}

/** Ports tried (in this order) the first time, before asking the system for any: outside the range it hands out. */
export const PREFERRED_PORTS = [8790, 8791, 8792, 8793, 8794, 8795, 8796, 8797, 8798, 8799];

/** Can we listen on this port right now? */
export function isPortFree(port) {
  return new Promise((resolve) => {
    const probe = createServer();
    probe.once('error', () => resolve(false));
    probe.listen(port, '127.0.0.1', () => probe.close(() => resolve(true)));
  });
}

/**
 * The first of `wanted` that is free, or any free port. The page keeps favourites, volume and the last channel per
 * origin (which includes the port), so the app asks for the same port every time and only gives it up if it is taken.
 */
export async function pickPort(wanted, { isFree = isPortFree, anyFree = freePort } = {}) {
  for (const port of wanted) {
    if (Number.isInteger(port) && (await isFree(port))) return port;
  }
  return anyFree();
}

/** Does a TDT local server answer on this port? */
export async function isTdtLocal(port, fetchImpl = fetch) {
  try {
    const response = await fetchImpl(`http://127.0.0.1:${port}/api/version`, { signal: AbortSignal.timeout(1500) });
    return (await response.json()).name === 'tdt-local';
  } catch {
    return false;
  }
}

/** Wait until the server answers (or fail with `message` after `timeoutMs`, or as soon as `aborted()` says it died). */
export async function waitForServer(port, { timeoutMs = 30000, aborted = () => false, fetchImpl = fetch } = {}) {
  const limit = Date.now() + timeoutMs;
  while (Date.now() < limit) {
    if (aborted()) throw new Error('el servidor se cerró al arrancar');
    if (await isTdtLocal(port, fetchImpl)) return;
    await new Promise((r) => setTimeout(r, 150));
  }
  throw new Error('el servidor no respondió a tiempo');
}

/**
 * Start the server on a free port. `command` is `{file, args, cwd, env}`: in development it is `python -m tdtlocal`; the
 * installed app will carry the packaged server instead.
 * @returns {{port: number, child: import('node:child_process').ChildProcess, url: string, exited: () => boolean}}
 */
export async function startServer(command, { onLine = () => {}, ports = [] } = {}) {
  const port = await pickPort(ports);
  const child = spawn(command.file, [...command.args, '--port', String(port), '--quit-button'], {
    cwd: command.cwd,
    env: { ...process.env, PYTHONUTF8: '1', ...command.env },
    stdio: ['ignore', 'pipe', 'pipe'],
    windowsHide: true,
  });
  let exited = false;
  const tail = [];
  const keep = (chunk) => {
    tail.push(String(chunk));
    if (tail.length > 40) tail.shift();
    for (const line of String(chunk).split(/\r?\n/)) if (line.trim()) onLine(line);
  };
  child.stdout.on('data', keep);
  child.stderr.on('data', keep);
  child.once('exit', () => { exited = true; });
  child.once('error', (error) => { tail.push(String(error)); exited = true; });
  try {
    await waitForServer(port, { aborted: () => exited });
  } catch (error) {
    child.kill();
    throw new Error(`${error.message}\n${tail.join('').slice(-1500)}`);
  }
  return { port, child, url: `http://127.0.0.1:${port}/`, exited: () => exited, log: () => tail.join('') };
}

/** Stop it politely (the server saves its state and stops whisper when asked), and by force if it does not obey. */
export async function stopServer(server, { graceMs = 5000 } = {}) {
  if (!server || server.exited()) return;
  const done = new Promise((resolve) => server.child.once('exit', resolve));
  try {
    await fetch(`http://127.0.0.1:${server.port}/api/quit`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: '{}',
      signal: AbortSignal.timeout(2000),
    });
  } catch { /* it may close before answering */ }
  const timer = setTimeout(() => server.child.kill(), graceMs);
  await done;
  clearTimeout(timer);
}
