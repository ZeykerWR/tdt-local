import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  FIELDS, TABS, collectChanges, describeDiagnosis, describeDownload, fieldsOf, formatBytes, percent,
} from '../../tdtlocal/static/js/lib/settings-form.js';

test('every field belongs to a tab and has a unique name', () => {
  const tabs = new Set(TABS.map((t) => t.id));
  assert.ok(FIELDS.every((f) => tabs.has(f.tab)));
  assert.equal(new Set(FIELDS.map((f) => f.name)).size, FIELDS.length);
  assert.ok(TABS.every((t) => fieldsOf(t.id).length > 0));
  for (const f of FIELDS) {
    assert.ok(['bool', 'number', 'text', 'url', 'path', 'select', 'json', 'secret'].includes(f.type), f.name);
    assert.ok(f.label, f.name);
    if (f.type === 'select') assert.ok(Object.keys(f.options).length > 1, f.name);
  }
});

test('collectChanges returns only what differs', () => {
  const original = { llm_url: 'http://a/v1', llm_model: '', llm_temperature: 0.2, ai_enabled: true, llm_api_key: '' };
  const current = { ...original, llm_model: 'qwen', ai_enabled: false };
  assert.deepEqual(collectChanges(original, current), { llm_model: 'qwen', ai_enabled: false });
  assert.deepEqual(collectChanges(original, original), {});
});

test('a secret is sent only when typed or explicitly removed', () => {
  const values = { llm_model: '' }; // like the real form: the secret is never read back into the values
  assert.deepEqual(collectChanges(values, values), {});
  assert.deepEqual(collectChanges(values, values, { secret: 'sk-1' }), { llm_api_key: 'sk-1' });
  assert.deepEqual(collectChanges(values, values, { removeSecret: true }), { llm_api_key: '' });
  assert.deepEqual(collectChanges(values, values, { secret: 'sk-1', removeSecret: true }), { llm_api_key: '' });
});

test('fields missing from the form are ignored', () => {
  assert.deepEqual(collectChanges({ llm_model: 'a', whisper_lang: 'es' }, { whisper_lang: 'en' }), { whisper_lang: 'en' });
});

test('formatBytes uses MB and GB with a decimal comma', () => {
  assert.equal(formatBytes(0), '0 MB');
  assert.equal(formatBytes(574_041_195), '547 MB');
  assert.equal(formatBytes(1024 * 1024 * 1024 * 1.5), '1,5 GB');
  assert.equal(formatBytes(1000), '1 MB');
});

test('percent is clamped and safe without a total', () => {
  assert.equal(percent(50, 200), 25);
  assert.equal(percent(300, 200), 100);
  assert.equal(percent(5, 0), 0);
});

test('describeDownload covers every state', () => {
  assert.equal(describeDownload(undefined), '');
  assert.equal(describeDownload({ state: 'idle' }), '');
  const running = describeDownload({ state: 'running', file: 'ggml-a.bin', done: 1024 * 1024 * 10, total: 1024 * 1024 * 100 });
  assert.match(running, /Descargando ggml-a\.bin: 10 MB de 100 MB \(10 %\)/);
  assert.match(describeDownload({ state: 'running', file: 'f', done: 5, total: 0 }), /^Descargando f: 1 MB$/);
  assert.match(describeDownload({ state: 'done', file: 'f', verified: true }), /verificado/);
  assert.match(describeDownload({ state: 'done', file: 'f', verified: false }), /no se pudo verificar/);
  assert.equal(describeDownload({ state: 'cancelled' }), 'Descarga cancelada.');
  assert.equal(describeDownload({ state: 'error', error: 'sin espacio' }), 'Error al descargar: sin espacio');
});

test('describeDiagnosis builds a checklist', () => {
  const good = describeDiagnosis({
    ffmpeg: '/usr/bin/ffmpeg', binary: { path: '/x/ws', found: true }, model: { path: '/m/a.bin', found: true, bytes: 5 * 1024 * 1024 },
    server_up: false, can_launch: true,
  });
  assert.equal(good.length, 4);
  assert.ok(good.every((r) => r.ok));
  const bad = describeDiagnosis({
    ffmpeg: '', binary: { path: 'ws', found: false }, model: { path: '', found: false, bytes: 0 }, server_up: false, can_launch: false,
  });
  assert.deepEqual(bad.map((r) => r.ok), [false, false, false, false]);
  assert.match(bad[2].text, /descarga uno/);
});
