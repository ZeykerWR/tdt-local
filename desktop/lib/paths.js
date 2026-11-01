// Where the desktop app keeps its files, and the port it remembers. Nothing here needs Electron.
import { copyFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { dirname, join } from 'node:path';

const APP_NAME = 'TDT local';

/** The per-user data folder of the server (the same rules as tdtlocal/paths.py), so the app and the server share it. */
export function userDataDir({ platform = process.platform, env = process.env, home = homedir() } = {}) {
  if (platform === 'win32') return join(env.LOCALAPPDATA || join(home, 'AppData', 'Local'), APP_NAME);
  if (platform === 'darwin') return join(home, 'Library', 'Application Support', APP_NAME);
  return join(env.XDG_DATA_HOME || join(home, '.local', 'share'), 'tdt-local');
}

/** The data folder of the server: `TDT_DATA_DIR`, the user's folder when installed, `data/` next to the code otherwise. */
export function dataDirFor({ packaged, repoRoot, env = process.env, ...rest }) {
  if (env.TDT_DATA_DIR) return env.TDT_DATA_DIR;
  return packaged ? userDataDir({ env, ...rest }) : join(repoRoot, 'data');
}

/** What Chromium and the app itself keep (page storage, plugin state, log): inside the data folder, so it goes with it. */
export const desktopDirFor = (dataDir) => join(dataDir, 'desktop');

/** Copy `from` to `to` unless `to` exists or `from` does not. Returns true when it copied. */
export function copyIfMissing(from, to) {
  if (!existsSync(from) || existsSync(to)) return false;
  mkdirSync(dirname(to), { recursive: true });
  copyFileSync(from, to);
  return true;
}

/** The port of the last run, or null. */
export function readPort(file) {
  try {
    const port = JSON.parse(readFileSync(file, 'utf8')).port;
    return Number.isInteger(port) && port >= 1024 && port <= 65535 ? port : null;
  } catch {
    return null;
  }
}

export function writePort(file, port) {
  mkdirSync(dirname(file), { recursive: true });
  writeFileSync(file, JSON.stringify({ port }) + '\n', 'utf8');
}
