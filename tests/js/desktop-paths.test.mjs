// Where the desktop app keeps its files and which port it asks for (desktop/lib/paths.js and pickPort in server.js).
import assert from 'node:assert/strict';
import { createServer } from 'node:net';
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';
import { copyIfMissing, dataDirFor, desktopDirFor, readPort, userDataDir, writePort } from '../../desktop/lib/paths.js';
import { PREFERRED_PORTS, isPortFree, pickPort, serverCommandFor } from '../../desktop/lib/server.js';

const slashes = (p) => p.replaceAll('\\', '/');

function temp() {
  const root = mkdtempSync(join(tmpdir(), 'tdt-paths-'));
  return { root, done: () => rmSync(root, { recursive: true, force: true }) };
}

test('the user folder follows the same rules as the server on each system', () => {
  assert.equal(slashes(userDataDir({ platform: 'win32', env: { LOCALAPPDATA: 'C:/L' }, home: 'C:/H' })), 'C:/L/TDT local');
  assert.equal(slashes(userDataDir({ platform: 'win32', env: {}, home: 'C:/H' })), 'C:/H/AppData/Local/TDT local');
  assert.equal(slashes(userDataDir({ platform: 'darwin', env: {}, home: '/Users/a' })), '/Users/a/Library/Application Support/TDT local');
  assert.equal(slashes(userDataDir({ platform: 'linux', env: { XDG_DATA_HOME: '/x' }, home: '/h' })), '/x/tdt-local');
  assert.equal(slashes(userDataDir({ platform: 'linux', env: {}, home: '/h' })), '/h/.local/share/tdt-local');
});

test('the data folder: TDT_DATA_DIR first, the user folder when installed, data/ next to the code in development', () => {
  const base = { repoRoot: '/repo', platform: 'linux', home: '/h' };
  assert.equal(dataDirFor({ ...base, packaged: true, env: { TDT_DATA_DIR: '/mine' } }), '/mine');
  assert.equal(slashes(dataDirFor({ ...base, packaged: true, env: {} })), '/h/.local/share/tdt-local');
  assert.equal(slashes(dataDirFor({ ...base, packaged: false, env: {} })), '/repo/data');
  assert.equal(slashes(desktopDirFor('/h/.local/share/tdt-local')), '/h/.local/share/tdt-local/desktop');
});

test('copyIfMissing copies once and never overwrites', () => {
  const { root, done } = temp();
  try {
    const from = join(root, 'old', 'plugins.json');
    const to = join(root, 'new', 'plugins.json');
    assert.equal(copyIfMissing(from, to), false); // nothing to copy
    mkdirSync(join(root, 'old'));
    writeFileSync(from, '{"enabled":["a"]}');
    assert.equal(copyIfMissing(from, to), true);
    assert.equal(readFileSync(to, 'utf8'), '{"enabled":["a"]}');
    writeFileSync(from, '{"enabled":["b"]}');
    assert.equal(copyIfMissing(from, to), false);
    assert.equal(readFileSync(to, 'utf8'), '{"enabled":["a"]}');
  } finally {
    done();
  }
});

test('the remembered port is read back, and junk is ignored', () => {
  const { root, done } = temp();
  try {
    const file = join(root, 'sub', 'port.json');
    assert.equal(readPort(file), null);
    writePort(file, 8791);
    assert.equal(readPort(file), 8791);
    for (const bad of ['not json', '{"port":"8791"}', '{"port":80}', '{"port":70000}', '{}']) {
      writeFileSync(file, bad);
      assert.equal(readPort(file), null, bad);
    }
  } finally {
    done();
  }
});

test('pickPort takes the first free port of the list, else any', async () => {
  const taken = new Set([8000, 8001]);
  const isFree = async (port) => !taken.has(port);
  const anyFree = async () => 49999;
  assert.equal(await pickPort([8000, 8001, 8002, 8003], { isFree, anyFree }), 8002);
  assert.equal(await pickPort([null, 8000, undefined], { isFree, anyFree }), 49999);
  assert.equal(await pickPort([], { isFree, anyFree }), 49999);
});

test('isPortFree tells a busy port from a free one, and the preferred ports are outside the ephemeral range', async () => {
  const holder = createServer();
  await new Promise((resolve) => holder.listen(0, '127.0.0.1', resolve));
  const { port } = holder.address();
  try {
    assert.equal(await isPortFree(port), false);
  } finally {
    await new Promise((resolve) => holder.close(resolve));
  }
  assert.equal(await isPortFree(port), true);
  assert.ok(PREFERRED_PORTS.every((p) => p > 1024 && p < 32768));
});

test('the server command: the frozen one when installed or asked for, python from the repository otherwise', () => {
  const base = { resourcesPath: '/res', repoRoot: '/repo', dataDir: '/data', platform: 'linux' };
  const installed = serverCommandFor({ ...base, packaged: true, env: {} });
  assert.equal(slashes(installed.file), '/res/server/tdt-local-server');
  assert.deepEqual(installed.args, []);
  assert.equal(slashes(installed.cwd), '/res/server');
  assert.deepEqual(installed.env, { TDT_DATA_DIR: '/data' });
  assert.equal(slashes(serverCommandFor({ ...base, packaged: true, env: {}, platform: 'win32' }).file), '/res/server/tdt-local-server.exe');

  const dev = serverCommandFor({ ...base, packaged: false, env: {} });
  assert.equal(dev.file, 'python3');
  assert.deepEqual(dev.args, ['-m', 'tdtlocal']);
  assert.equal(dev.cwd, '/repo');
  assert.equal(serverCommandFor({ ...base, packaged: false, env: {}, platform: 'win32' }).file, 'python');
  assert.equal(serverCommandFor({ ...base, packaged: false, env: { TDT_PYTHON: '/py' } }).file, '/py');

  const asked = serverCommandFor({ ...base, packaged: false, env: { TDT_SERVER_EXE: '/x/y/server.exe' } });
  assert.equal(asked.file, '/x/y/server.exe');
  assert.equal(slashes(asked.cwd), '/x/y');
});
