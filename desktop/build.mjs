// Package the desktop app: Electron + this folder + the frozen server + the plugins that come with it.
//
//   python packaging/build.py --server-only      # first: dist/tdt-local-server/
//   cd desktop && npm run pack                    # then: dist/electron/tdt-local-<platform>-<arch>/
//
// Options: --server <dir> (default ../dist/tdt-local-server), --out <dir> (default ../dist/electron).
// Packaging is for the system it runs on: build on each system for that system (the frozen server is native too).
import { packager } from '@electron/packager';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { iconFor, readVersion, stageExtras, trimLocales } from './lib/pack.js';

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(here, '..');

const option = (name, fallback) => {
  const at = process.argv.indexOf(name);
  return at > 0 && process.argv[at + 1] ? resolve(process.argv[at + 1]) : fallback;
};

const version = readVersion(repoRoot);
const out = option('--out', join(repoRoot, 'dist', 'electron'));
const extras = stageExtras({
  repoRoot,
  serverDir: option('--server', join(repoRoot, 'dist', 'tdt-local-server')),
  stageDir: join(repoRoot, 'build', 'electron-extra'),
});

const paths = await packager({
  dir: here,
  out,
  overwrite: true,
  name: 'TDT local',
  executableName: 'tdt-local',
  appVersion: version,
  appCopyright: 'Copyright 2026 TDT local contributors. Apache License 2.0.',
  icon: iconFor(process.platform, repoRoot),
  asar: true,
  prune: true,
  extraResource: extras,
  // only what the app runs: not this script, not the lock file
  ignore: [/^\/build\.mjs$/, /^\/package-lock\.json$/],
  afterExtract: [
    async ({ buildPath }) => {
      const gone = trimLocales(buildPath);
      if (gone) console.log(`idiomas de Chromium quitados: ${gone}`);
    },
  ],
  win32metadata: { CompanyName: 'TDT local contributors', FileDescription: 'TDT local', ProductName: 'TDT local' },
  appBundleId: 'io.github.cibernicola.tdt-local',
  appCategoryType: 'public.app-category.video',
});

for (const path of paths) console.log('Aplicación empaquetada:', path);
