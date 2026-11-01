// The log of the desktop app (desktop/lib/logbook.js) and the text of the "Registro" tab of the settings.
import assert from 'node:assert/strict';
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';

import { Logbook, levelOf as serverLevel, scrub } from '../../desktop/lib/logbook.js';
import { filterLines, levelOf, summarize } from '../../tdtlocal/static/js/lib/logs-panel.js';

const fixed = () => new Date('2026-11-01T19:45:07Z');

function temp() {
  const dir = mkdtempSync(join(tmpdir(), 'tdt-logs-'));
  return { dir, done: () => rmSync(dir, { recursive: true, force: true }) };
}

test('a line carries the time, the level and where it comes from, one line per line of text', () => {
  const book = new Logbook({ now: fixed });
  assert.deepEqual(book.add('app', 'INFO', 'arranca'), ['2026-11-01 19:45:07 INFO  [app] arranca']);
  assert.deepEqual(book.add('servidor', 'ERROR', 'Traceback:\r\n\r\n  File x\n'), [
    '2026-11-01 19:45:07 ERROR [servidor] Traceback:',
    '2026-11-01 19:45:07 ERROR [servidor]   File x',
  ]);
  assert.equal(book.add('app', 'NOPE', 'x')[0].includes(' INFO  '), true); // an unknown level is INFO
  assert.deepEqual(book.add('app', 'INFO', '   '), []); // nothing to say
  assert.equal(book.lines().length, 4);
});

test('long lines are cut and only the last lines are kept', () => {
  const book = new Logbook({ max: 3, now: fixed });
  assert.ok(book.add('x', 'INFO', 'a'.repeat(2000))[0].length < 700);
  for (let i = 0; i < 5; i++) book.add('x', 'INFO', 'línea ' + i);
  assert.deepEqual(book.lines().map((l) => l.slice(-7)), ['línea 2', 'línea 3', 'línea 4']);
  assert.equal(book.lines(2).length, 2);
  assert.equal(book.text(1), book.lines(1)[0]);
});

test('keys and tokens that travel in an address or a header are hidden', () => {
  assert.equal(scrub('GET /x?token=abc123&b=1'), 'GET /x?token=[oculto]&b=1');
  assert.equal(scrub('https://a/b?sid=XYZ789&auth=qq9999'), 'https://a/b?sid=[oculto]&auth=[oculto]');
  assert.equal(scrub('Authorization: Bearer abcdef'), 'Authorization: [oculto]');
  assert.equal(scrub('Cookie: a=1; b=2'), 'Cookie: [oculto]');
  assert.equal(scrub('llevaba Bearer eyJhbGciOi.payload.firma y más'), 'llevaba Bearer [oculto] y más');
  assert.equal(scrub('api_key=sk-123456'), 'api_key=[oculto]');
  assert.equal(scrub('nada que ocultar: canal=La 1'), 'nada que ocultar: canal=La 1');
  const book = new Logbook({ now: fixed });
  assert.ok(!book.add('app', 'INFO', 'abre https://x/y?token=SECRET99')[0].includes('SECRET99'));
});

test('the log is also written to a file, which rolls over when it is big, and a broken disk does not stop it', () => {
  const { dir, done } = temp();
  try {
    const file = join(dir, 'logs', 'tdt-local.log');
    const book = new Logbook({ file, maxBytes: 200, now: fixed });
    book.add('app', 'INFO', 'primera');
    assert.match(readFileSync(file, 'utf8'), /primera\n$/);
    for (let i = 0; i < 6; i++) book.add('app', 'INFO', 'relleno número ' + i + ' '.repeat(20));
    assert.ok(existsSync(file + '.1')); // the previous file is kept once
    assert.ok(readFileSync(file, 'utf8').length < 600);

    writeFileSync(join(dir, 'ocupado'), 'soy un archivo');
    const broken = new Logbook({ file: join(dir, 'ocupado', 'dentro.log'), now: fixed }); // a folder cannot be made inside a file
    assert.equal(broken.add('app', 'WARN', 'sigue en memoria').length, 1);
    assert.equal(broken.fileOk, false);
    assert.equal(broken.lines().length, 1);
  } finally { done(); }
});

test('the lines of the Python server get a level from what they say', () => {
  assert.equal(serverLevel('Traceback (most recent call last):'), 'ERROR');
  assert.equal(serverLevel('19:45:07 AVISO: accesible desde la red local'), 'WARN');
  assert.equal(serverLevel('19:45:07 TDT local en http://127.0.0.1:8788/'), 'INFO');
});

test('the tab reads the level of a line, filters and counts', () => {
  const lines = [
    '2026-11-01 19:45:07 INFO  [app] arranca',
    '2026-11-01 19:45:08 WARN  [plugins] x no se puede usar',
    '2026-11-01 19:45:09 ERROR [pagina] Failed to load resource',
    '2026-11-01 19:45:10 INFO  [pagina] hola ERROR dentro del texto',
    'una línea sin formato',
  ];
  assert.deepEqual(lines.map(levelOf), ['INFO', 'WARN', 'ERROR', 'INFO', 'INFO']);
  assert.deepEqual(filterLines(lines, 'all', 400), lines);
  assert.deepEqual(filterLines(lines, 'problems'), [lines[1], lines[2]]);
  assert.deepEqual(filterLines(lines, 'all', 2), lines.slice(-2));
  assert.equal(summarize(lines), '5 líneas (1 aviso, 1 error)');
  assert.equal(summarize([lines[0]]), '1 línea');
  assert.equal(summarize([]), '0 líneas');
  assert.equal(summarize([lines[1], lines[1], lines[2], lines[2]]), '4 líneas (2 avisos, 2 errores)');
});
