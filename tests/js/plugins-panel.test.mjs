// What the "Plugins" tab of the settings says about each plugin (the tab only exists in the desktop app).
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { describePlugin, hostsOf, summarize } from '../../tdtlocal/static/js/lib/plugins-panel.js';

const bridge = {
  name: 'TDT local · puente con Atresplayer',
  version: '1.1.0',
  description: 'Cuenta a TDT local cuándo hay publicidad.',
  source: 'incluido con la aplicación',
  sites: ['https://www.atresplayer.com/embed/live/*', 'https://atresplayer.com/embed/live/*'],
  problems: [],
  enabled: false,
};

test('the sites of a plugin are shown as hosts, once each', () => {
  assert.deepEqual(hostsOf(bridge.sites), ['www.atresplayer.com', 'atresplayer.com']);
  assert.deepEqual(hostsOf(['https://a.com/x/*', 'http://a.com/y', '*://b.com:8080/*']), ['a.com', 'b.com:8080']);
  assert.deepEqual(hostsOf(['rubbish', undefined]), []);
  assert.deepEqual(hostsOf(), []);
});

test('a plugin is described with where it acts and where it comes from', () => {
  const d = describePlugin(bridge);
  assert.equal(d.title, 'TDT local · puente con Atresplayer 1.1.0');
  assert.equal(d.acts, 'Actúa solo en: www.atresplayer.com, atresplayer.com.');
  assert.equal(d.source, 'Viene de: incluido con la aplicación.');
  assert.deepEqual([d.usable, d.on], [true, false]);
  assert.equal(describePlugin({ ...bridge, enabled: true }).on, true);
});

test('a plugin with problems cannot be on, whatever the saved state says', () => {
  const d = describePlugin({ ...bridge, enabled: true, problems: ['pide «permissions»'] });
  assert.deepEqual([d.usable, d.on], [false, false]);
  assert.deepEqual(d.problems, ['pide «permissions»']);
});

test('a plugin with no version or source does not show empty words', () => {
  const d = describePlugin({ ...bridge, version: '', source: '', sites: [] });
  assert.equal(d.title, bridge.name);
  assert.equal(d.source, '');
  assert.equal(d.acts, '');
});

test('the summary counts plugins and how many are on', () => {
  assert.equal(summarize([]), 'No hay ningún plugin.');
  assert.equal(summarize([bridge]), '1 plugin, ninguno activado.');
  assert.equal(summarize([{ ...bridge, enabled: true }]), '1 plugin, 1 activado.');
  assert.equal(summarize([{ ...bridge, enabled: true }, { ...bridge, enabled: true }, bridge]), '3 plugins, 2 activados.');
  assert.equal(summarize([{ ...bridge, enabled: true, problems: ['x'] }]), '1 plugin, ninguno activado.');
});
