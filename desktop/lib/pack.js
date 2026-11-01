// Helpers of desktop/build.mjs, apart so they can be tested without packaging anything. Nothing here needs Electron.
import { cpSync, existsSync, mkdirSync, readdirSync, readFileSync, rmSync, statSync } from 'node:fs';
import { join } from 'node:path';

/** The version of the program, from tdtlocal/__init__.py (the same file build.py and the release check read). */
export function versionFrom(initText) {
  const match = /^__version__\s*=\s*["']([^"']+)["']/m.exec(initText);
  if (!match) throw new Error('no se encuentra __version__ en tdtlocal/__init__.py');
  return match[1];
}

/** Chromium locales kept in the package (Windows and Linux): the interface is in Spanish, with English as fallback. */
export const KEPT_LOCALES = new Set(['en-US.pak', 'es.pak', 'es-419.pak']);

/** The `locales/*.pak` files of an extracted Electron that can go. */
export function localesToRemove(files) {
  return files.filter((name) => name.endsWith('.pak') && !KEPT_LOCALES.has(name));
}

/** Delete the Chromium locales we do not show. Returns how many it removed. */
export function trimLocales(electronDir) {
  const dir = join(electronDir, 'locales');
  if (!existsSync(dir)) return 0;
  const gone = localesToRemove(readdirSync(dir));
  for (const name of gone) rmSync(join(dir, name));
  return gone.length;
}

/** The folders of `toolsDir` that are plugins (they have a manifest.json). */
export function pluginDirs(toolsDir) {
  return readdirSync(toolsDir)
    .filter((name) => statSync(join(toolsDir, name)).isDirectory() && existsSync(join(toolsDir, name, 'manifest.json')))
    .sort();
}

/**
 * What goes next to the app (`resources/`): the frozen server as `server/`, the plugins that come with it as
 * `plugins/<name>/` and the icon of the tray and windows as `icon.png`. Returns the paths to hand to the packager.
 */
export function stageExtras({ repoRoot, serverDir, stageDir }) {
  if (!existsSync(join(serverDir, process.platform === 'win32' ? 'tdt-local-server.exe' : 'tdt-local-server'))) {
    throw new Error(`no hay servidor congelado en ${serverDir}: ejecuta antes «python packaging/build.py --server-only»`);
  }
  rmSync(stageDir, { recursive: true, force: true });
  mkdirSync(stageDir, { recursive: true });
  cpSync(serverDir, join(stageDir, 'server'), { recursive: true });
  const plugins = join(stageDir, 'plugins');
  mkdirSync(plugins);
  for (const name of pluginDirs(join(repoRoot, 'tools'))) cpSync(join(repoRoot, 'tools', name), join(plugins, name), { recursive: true });
  cpSync(join(repoRoot, 'packaging', 'icons', 'icon-256.png'), join(stageDir, 'icon.png'));
  return [join(stageDir, 'server'), plugins, join(stageDir, 'icon.png')];
}

/** The icon of the executable without extension, as the packager wants it (it adds .ico or .icns itself). */
export function iconFor(platform, repoRoot) {
  const icons = join(repoRoot, 'packaging', 'icons');
  if (platform === 'win32' || platform === 'darwin') return join(icons, 'icon');
  return undefined; // Linux takes the icon of the .desktop entry, not of the executable
}

export function readVersion(repoRoot) {
  return versionFrom(readFileSync(join(repoRoot, 'tdtlocal', '__init__.py'), 'utf8'));
}
