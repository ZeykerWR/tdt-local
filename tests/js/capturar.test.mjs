import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import vm from 'node:vm';

import { parseAddLink } from '../../tdtlocal/static/js/lib/addlink.js';
import { ATRES_ORIGIN, ContentClock, audioMessage, fxMessage, parseBridge } from '../../tdtlocal/static/js/lib/bridge.js';
import { GROUPS, atresEmbed, atresLink, atresWeb, missingOf } from '../../tdtlocal/static/js/lib/embeds.js';

// tools/capturar-directo.js is a script to paste in a console: run it the way a test can, as a CommonJS module
const source = readFileSync(new URL('../../tools/capturar-directo.js', import.meta.url), 'utf8');
const sandbox = { module: { exports: {} }, console };
vm.runInNewContext(source, sandbox);
const { listas, principal, nombreDe, enlaceTdt } = sandbox.module.exports;

const entry = (name, startTime) => ({ name, startTime });

test('listas keeps the .m3u8 requests, once each, in order of first request, with the newest token', () => {
  const found = listas([
    entry('https://cdn.example/live/master.m3u8?token=a', 10),
    entry('https://cdn.example/live/seg1.ts', 11),
    entry('https://cdn.example/live/720p/chunklist.m3u8?token=a', 12),
    entry('https://cdn.example/live/720p/chunklist.m3u8?token=b', 20),
    entry('https://cdn.example/thumb.png', 21),
    entry('https://cdn.example/live/master.m3u8?token=c', 30),
  ]);
  assert.deepEqual(Array.from(found, (l) => l.url), [
    'https://cdn.example/live/master.m3u8?token=c',
    'https://cdn.example/live/720p/chunklist.m3u8?token=b',
  ]);
  assert.equal(listas([entry('https://x/a.mp4', 1), entry('https://x/notm3u8', 2)]).length, 0);
});

test('principal prefers the master playlist over one quality', () => {
  const l = (url, t) => ({ url, t });
  assert.equal(principal([l('https://c/720p/chunklist.m3u8?t=1', 1), l('https://c/live/index.m3u8?t=1', 2)]).url, 'https://c/live/index.m3u8?t=1');
  assert.equal(principal([l('https://c/live/master.m3u8', 1), l('https://c/live/chunklist_1.m3u8', 2)]).url, 'https://c/live/master.m3u8');
  assert.equal(principal([l('https://c/audio_1.m3u8', 1), l('https://c/video_1.m3u8', 2)]).url, 'https://c/audio_1.m3u8'); // nothing better: the first
});

test('nombreDe takes the channel out of a page title', () => {
  assert.equal(nombreDe('La Sexta en directo | atresplayer'), 'La Sexta');
  assert.equal(nombreDe('Antena 3 en directo - Atresplayer'), 'Antena 3');
  assert.equal(nombreDe(''), 'Canal propio');
  assert.equal(nombreDe('x'.repeat(200)).length, 80);
});

test('enlaceTdt builds the address with the fragment, and the Atresplayer headers only there', () => {
  const url = 'https://cdn.example/a/master.m3u8?hdnts=exp=1~hmac=ab&x=1';
  const atres = enlaceTdt(8788, url, 'La Sexta', 'www.atresplayer.com');
  assert.ok(atres.startsWith('http://127.0.0.1:8788/#add='));
  assert.ok(atres.endsWith('&hdr=atres'));
  assert.ok(!atres.includes('?hdnts')); // the link is encoded: it cannot be mistaken for the address's own query
  assert.ok(!enlaceTdt(8788, url, 'Otro', 'www.ejemplo.com').includes('hdr='));
  assert.ok(!enlaceTdt(8788, url, 'Otro', 'notatresplayer.com.evil.example').includes('hdr='));
});

test('what the snippet builds, the page understands', () => {
  const url = 'https://cdn.example/a/master.m3u8?hdnts=exp=1~hmac=ab&x=1';
  const link = enlaceTdt(8788, url, 'La Sexta', 'www.atresplayer.com');
  assert.deepEqual(parseAddLink(new URL(link).hash), { url, name: 'La Sexta', kind: 'tv', hdr: 'atres' });
});

test('parseAddLink only accepts a link to http(s), and cleans the rest', () => {
  assert.equal(parseAddLink(''), null);
  assert.equal(parseAddLink('#other=1'), null);
  assert.equal(parseAddLink('#add=javascript:alert(1)'), null);
  assert.equal(parseAddLink('#add=ftp://x/a.m3u8'), null);
  assert.equal(parseAddLink('#add=' + encodeURIComponent('https://x/a b.m3u8')), null);
  assert.equal(parseAddLink('#add=' + encodeURIComponent('https://x/' + 'a'.repeat(5000))), null);
  const ok = parseAddLink('#add=' + encodeURIComponent('https://x/a.m3u8') + '&name=' + 'N'.repeat(200) + '&kind=radio&hdr=raro');
  assert.equal(ok.url, 'https://x/a.m3u8');
  assert.equal(ok.name.length, 80);
  assert.equal(ok.kind, 'radio');
  assert.equal(ok.hdr, '');
  assert.equal(parseAddLink('#add=' + encodeURIComponent('https://x/a.m3u8') + '&kind=otro').kind, 'tv');
});

test('atresEmbed only recognises the official embeddable live player of Atresplayer', () => {
  assert.equal(atresEmbed('https://www.atresplayer.com/embed/live/lasexta/'), 'https://www.atresplayer.com/embed/live/lasexta/');
  assert.equal(atresEmbed('https://www.atresplayer.com/embed/live/LaSexta'), 'https://www.atresplayer.com/embed/live/lasexta/');
  assert.equal(atresEmbed('https://www.atresplayer.com/embed/live/antena3/?x=1'), 'https://www.atresplayer.com/embed/live/antena3/');
  assert.equal(atresEmbed('http://www.atresplayer.com/embed/live/lasexta/'), null);
  assert.equal(atresEmbed('https://www.atresplayer.com.evil.example/embed/live/lasexta/'), null);
  assert.equal(atresEmbed('https://evil.example/https://www.atresplayer.com/embed/live/lasexta/'), null);
  assert.equal(atresEmbed('https://www.atresplayer.com/directos/lasexta/'), null);
  assert.equal(atresEmbed('https://atres-live-ssai.atresmedia.com/x/master.m3u8'), null);
  assert.equal(atresEmbed(''), null);
  assert.equal(atresLink('lasexta'), 'https://www.atresplayer.com/embed/live/lasexta/');
  assert.equal(atresWeb('https://www.atresplayer.com/embed/live/lasexta/'), 'https://www.atresplayer.com/directos/lasexta/');
  assert.equal(atresWeb('https://example.org/a.m3u8'), '');
});

test('the Atresmedia group is made of channels that Atresplayer can embed', () => {
  assert.deepEqual(Object.keys(GROUPS), ['atresmedia']); // Mediaset forbids being embedded: it is not offered
  const atres = GROUPS.atresmedia.channels;
  assert.deepEqual(Array.from(atres, (c) => c.name), ['Antena 3', 'La Sexta', 'Neox', 'Nova', 'Mega', 'Atreseries']);
  for (const c of atres) {
    assert.ok(atresEmbed(c.sources[0]), c.name); // its source is an embeddable player
    assert.equal(atresWeb(c.sources[0]), c.web, c.name);
  }
});

test('Atresmedia channels carry the guide id and the icon of the community guide', () => {
  for (const c of GROUPS.atresmedia.channels) {
    assert.ok(c.epg && !c.epg.includes('\n'), c.name);
    assert.match(c.logo, /^https:\/\/raw\.githubusercontent\.com\/davidmuma\/picons_dobleM\/master\/icon\/[^/]+\.png$/, c.name);
  }
  const byName = Object.fromEntries(GROUPS.atresmedia.channels.map((c) => [c.name, c]));
  assert.equal(byName['La Sexta'].epg, 'La Sexta HD');
  assert.equal(byName['Antena 3'].epg, 'Antena 3 HD');
  assert.equal(byName['Antena 3'].logo.endsWith('/Antena%203.png'), true);
});

test('missingOf only asks for the channels that still need the player or a guide', () => {
  assert.equal(missingOf('atresmedia', []).length, 6);
  const own = (name, epg, ...urls) => ({ custom: true, name, epg, sources: urls.map((u) => ({ u })) });
  const player = atresLink('lasexta');
  const have = [own('La Sexta', 'La Sexta HD', player), { custom: false, sources: [{ u: atresLink('neox') }] }];
  const left = Array.from(missingOf('atresmedia', have), (c) => c.name);
  assert.ok(!left.includes('La Sexta'));
  assert.ok(left.includes('Neox')); // a channel of the lists is not an own channel
  // a channel of the same name that only has a stream is not skipped: the player is added to it
  assert.ok(Array.from(missingOf('atresmedia', [own('La Sexta', '', 'https://cdn.example/lasexta/master.m3u8')]), (c) => c.name).includes('La Sexta'));
  // it has the player but no guide yet (added before the guide existed): it is asked for again, to get one
  assert.ok(Array.from(missingOf('atresmedia', [own('La Sexta', '', player)]), (c) => c.name).includes('La Sexta'));
  // complete: nothing left
  assert.equal(missingOf('atresmedia', Array.from(GROUPS.atresmedia.channels, (c) => own(c.name, c.epg, 'https://x/y.m3u8', ...c.sources))).length, 0);
});

// the bridge script (tools/puente-atresplayer/puente.user.js) is also loaded the way a test can
const bridgeSource = readFileSync(new URL('../../tools/puente-atresplayer/puente.user.js', import.meta.url), 'utf8');
const bridgeBox = { module: { exports: {} } };
vm.runInNewContext(bridgeSource, bridgeBox);
const { esEtiquetaDePublicidad, esTdtLocal } = bridgeBox.module.exports;

test('the bridge recognises the "Publicidad" label and nothing like it in a title', () => {
  const known = [
    'Publicidad', '  publicidad ', 'PUBLICIDAD', 'Publicidad · 0:30', 'Publicidad 1 de 3',
    'El canal que estás viendo en directo se encuentra en estos momentos en publicidad', // the notice of the live breaks
    'El canal que estás viendo se encuentra en este momento en publicidad.',
  ];
  for (const text of known) assert.equal(esEtiquetaDePublicidad(text), true, text);
  const unrelated = [
    '', 'Directo', 'Sin publicidad hoy', 'La publicidad en televisión', 'Publicidad ' + 'x'.repeat(60),
    'Programa sobre cómo el canal se encuentra en estos momentos en publicidad y en crisis ' + 'x'.repeat(100),
    'El canal que estás viendo en directo se encuentra en estos momentos emitiendo el programa',
  ];
  for (const text of unrelated) assert.equal(esEtiquetaDePublicidad(text), false, text);
});

test('the bridge only works for TDT local on this computer', () => {
  assert.equal(esTdtLocal('http://127.0.0.1:8788'), true);
  assert.equal(esTdtLocal('http://localhost:9000'), true);
  assert.equal(esTdtLocal('http://[::1]:8788'), true);
  assert.equal(esTdtLocal('https://evil.example'), false);
  assert.equal(esTdtLocal('http://127.0.0.1.evil.example'), false);
  assert.equal(esTdtLocal('https://localhost.evil.example:1'), false);
  assert.equal(esTdtLocal(''), undefined); // the browser does not say (Firefox)
});

test('parseBridge only accepts what the iframe of the tile says from Atresplayer', () => {
  const frame = {};
  const say = (data, extra = {}) => parseBridge({ origin: ATRES_ORIGIN, source: frame, data, ...extra }, frame);
  assert.deepEqual(say({ source: 'tdt-bridge', type: 'ready' }), { kind: 'ready' });
  assert.deepEqual(say({ source: 'tdt-bridge', type: 'state', ad: true }), { kind: 'ad', on: true, playing: false });
  assert.deepEqual(say({ source: 'tdt-bridge', type: 'state', ad: false, playing: true }), { kind: 'ad', on: false, playing: true });
  assert.deepEqual(say({ source: 'tdt-bridge', type: 'state', ad: 'yes', playing: 'si' }), { kind: 'ad', on: false, playing: false });
  assert.equal(say({ source: 'tdt-bridge', type: 'otra' }), null);
  assert.equal(say({ source: 'otro', type: 'ready' }), null);
  assert.equal(say('ready'), null);
  assert.equal(say(null), null);
  assert.equal(say({ source: 'tdt-bridge', type: 'ready' }, { origin: 'https://evil.example' }), null);
  assert.equal(say({ source: 'tdt-bridge', type: 'ready' }, { origin: 'https://www.atresplayer.com.evil.example' }), null);
  assert.equal(say({ source: 'tdt-bridge', type: 'ready' }, { source: {} }), null); // another window
  assert.equal(parseBridge({ origin: ATRES_ORIGIN, source: null, data: { source: 'tdt-bridge', type: 'ready' } }, null), null);
});

test('audioMessage asks for the user volume and mute, kept in range', () => {
  assert.deepEqual(audioMessage({ v: 0.4, m: true }), { source: 'tdt-local', type: 'audio', muted: true, volume: 0.4 });
  assert.equal(audioMessage({ v: 7, m: false }).volume, 1);
  assert.equal(audioMessage({ v: -1, m: false }).volume, 0);
  assert.equal(audioMessage({ v: NaN, m: false }).volume, 1);
});

test('the bridge is also an extension that can be loaded as it is, matching what the script says it is for', () => {
  const manifest = JSON.parse(readFileSync(new URL('../../tools/puente-atresplayer/manifest.json', import.meta.url), 'utf8'));
  assert.equal(manifest.manifest_version, 3);
  assert.equal(manifest.permissions, undefined); // it asks for nothing
  assert.equal(manifest.host_permissions, undefined);
  const [content] = manifest.content_scripts;
  assert.deepEqual(content.js, ['audio-chain.js', 'puente.user.js']); // the sound chain first: the script uses it
  assert.equal(content.all_frames, true); // the player is an iframe of TDT local
  const header = [...bridgeSource.matchAll(/^\/\/ @match\s+(\S+)/gm)].map((m) => m[1]);
  assert.deepEqual([...content.matches].sort(), header.sort()); // the same pages as the userscript header
  for (const pattern of content.matches) assert.match(pattern, /^https:\/\/(www\.)?atresplayer\.com\/embed\/live\/\*$/);
});

test('ContentClock tells the start-up ad (no programme before it) from a break', () => {
  const clock = new ContentClock();
  const at = (seconds) => seconds * 1000;
  assert.equal(clock.update({ on: false, playing: false }, at(0)), 0); // the start screen
  assert.equal(clock.update({ on: true, playing: true }, at(5)), 0); // start-up ad: nothing before it
  assert.equal(clock.update({ on: true, playing: true }, at(9)), 0);
  assert.equal(clock.update({ on: false, playing: true }, at(30)), 0); // programme starts
  assert.equal(clock.update({ on: false, playing: true }, at(34)), 4);
  assert.equal(clock.update({ on: false, playing: true }, at(60)), 30);
  assert.equal(clock.update({ on: true, playing: true }, at(64)), 34); // a break after 34 s of programme
  assert.equal(clock.update({ on: true, playing: true }, at(68)), 0); // and it does not count while in the ad
  assert.equal(clock.update({ on: false, playing: true }, at(100)), 0);
  assert.equal(clock.update({ on: true, playing: true }, at(112)), 12); // the ad comes back after 12 s: still short
  assert.equal(clock.update({ on: false, playing: false }, at(120)), 0); // the player stopped
  assert.equal(clock.update({ on: false, playing: false }, at(124)), 0);
});

test('parseBridge reads the meter of the leveler inside the player, and nothing else of it', () => {
  const frame = {};
  const say = (data) => parseBridge({ origin: ATRES_ORIGIN, source: frame, data }, frame);
  assert.deepEqual(say({ source: 'tdt-bridge', type: 'meter', loudness: -23.4, gainDb: 3.1 }), { kind: 'meter', loudness: -23.4, gainDb: 3.1 });
  assert.deepEqual(say({ source: 'tdt-bridge', type: 'meter', loudness: null, gainDb: 0 }), { kind: 'meter', loudness: null, gainDb: 0 });
  assert.deepEqual(say({ source: 'tdt-bridge', type: 'meter', loudness: 'alto', gainDb: Infinity }), { kind: 'meter', loudness: null, gainDb: null });
});

test('fxMessage sends the leveler and the equalizer as plain data', () => {
  const fx = { level: { on: true, target: -20, boost: 12, extra: 1 }, eq: { on: false, gains: new Float32Array(3).fill(2) } };
  const message = fxMessage(fx);
  assert.deepEqual(message.level, { on: true, target: -20, boost: 12 });
  assert.deepEqual(message.eq, { on: false, gains: [2, 2, 2] });
  assert.equal(message.source, 'tdt-local');
  assert.equal(message.type, 'fx');
  assert.doesNotThrow(() => structuredClone(message)); // it can go through postMessage
});
