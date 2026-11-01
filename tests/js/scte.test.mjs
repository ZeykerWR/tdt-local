import assert from 'node:assert/strict';
import { test } from 'node:test';

import { alertText, arrivals, kindLabel, statusLine, summaryText } from '../../tdtlocal/static/js/lib/scte.js';

const status = (extra = {}) => ({
  enabled: true, scope: 'all', interval: 60, events: 0,
  scan: { running: false, done: 0, total: 0, errors: 0, last: null }, ...extra,
});

test('kinds have a Spanish name and unknown ones are shown as they are', () => {
  assert.equal(kindLabel('cue-out'), 'Empieza una pausa de anuncios');
  assert.equal(kindLabel('algo-nuevo'), 'algo-nuevo');
});

test('alertText joins the label and the detail', () => {
  assert.equal(alertText({ kind: 'cue-out', detail: '30 s' }), 'Empieza una pausa de anuncios · 30 s');
  assert.equal(alertText({ kind: 'cue-in', detail: '' }), 'Termina la pausa de anuncios');
});

test('arrivals: nothing on the first look, then only what is newer', () => {
  const events = [{ id: 1 }, { id: 2 }, { id: 3 }];
  assert.deepEqual(arrivals(events, null), []);
  assert.deepEqual(arrivals(events, 1).map((e) => e.id), [2, 3]);
  assert.deepEqual(arrivals(events, 3), []);
  assert.deepEqual(arrivals([], 0), []);
});

test('statusLine explains each situation', () => {
  assert.match(statusLine(status({ enabled: false })), /desactivada/);
  assert.match(statusLine(status({ scope: 'viewing' })), /lo que estás viendo/);
  assert.match(statusLine(status()), /todos los canales con directo cada 60 s/);
  assert.match(statusLine(status({ scope: 'list' })), /tu lista/);
  const running = statusLine(status({ scan: { running: true, done: 3, total: 10, errors: 0, last: null } }));
  assert.match(running, /3 de 10/);
  const done = statusLine(status({ scan: { running: false, done: 10, total: 10, errors: 2, last: 1000 } }), 1000);
  assert.match(done, /ahora mismo/);
  assert.match(done, /2 que no respondieron/);
});

test('summaryText counts markers and channels', () => {
  assert.equal(summaryText([]), 'Todavía no se ha encontrado ninguna marca.');
  assert.equal(summaryText([{ count: 1 }]), '1 marca en 1 canal.');
  assert.equal(summaryText([{ count: 2 }, { count: 3 }]), '5 marcas en 2 canales.');
});
