import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  altChannel, audioTarget, audioTouched, duckedGain, reactionTo, remainingOf, segmentStart, startText, tooShort, untilMarker, waitFor,
} from '../../tdtlocal/static/js/lib/adbreak.js';

const cfg = { audio: 'mute', lower_percent: 25, screen: 'keep', channel: '', web_url: '', min_seconds: 10, unknown_seconds: 120, on_touch: 'respect' };
const ev = (kind, extra = {}) => ({ kind, channel: 'la-1', ...extra });

test('segmentStart finds a segment by name whatever the URL around it', () => {
  const starts = new Map([
    ['https://h.example/live/seg1.ts?token=a', 10],
    ['https://h.example/live/seg2.ts?token=a', 16],
  ]);
  assert.equal(segmentStart(starts, 'seg2.ts'), 16);
  assert.equal(segmentStart(starts, 'seg9.ts'), undefined);
  assert.equal(segmentStart(starts, undefined), undefined);
  assert.equal(segmentStart(new Map([['https://h/a%20b.ts', 5]]), 'a b.ts'), 5);
});

test('segmentStart prefers the newest when a name repeats', () => {
  const starts = new Map([['https://h/1/seg.ts', 10], ['https://h/2/seg.ts', 99]]);
  assert.equal(segmentStart(starts, 'seg.ts'), 99);
});

test('waitFor never goes negative and follows the playback rate', () => {
  assert.equal(waitFor(20, 12), 8);
  assert.equal(waitFor(20, 25), 0);
  assert.equal(waitFor(20, 10, 2), 5);
  assert.equal(waitFor(20, 10, 0), 10);
});

test('remainingOf: declared length minus what already went by, or the assumed length', () => {
  assert.deepEqual(remainingOf(ev('cue-out', { duration: 30 }), cfg), { known: true, seconds: 30 });
  assert.deepEqual(remainingOf(ev('cue-out-cont', { duration: 60, elapsed: 45 }), cfg), { known: true, seconds: 15 });
  assert.deepEqual(remainingOf(ev('cue-out'), cfg), { known: false, seconds: 120 });
  assert.deepEqual(remainingOf(ev('cue-out-cont', { duration: 30, elapsed: 99 }), cfg), { known: true, seconds: 0 });
});

test('tooShort only applies to breaks that say how long they are', () => {
  assert.equal(tooShort(ev('cue-out', { duration: 5 }), cfg), true);
  assert.equal(tooShort(ev('cue-out', { duration: 10 }), cfg), false);
  assert.equal(tooShort(ev('cue-out'), cfg), false);
  assert.equal(tooShort(ev('cue-out-cont', { duration: 60, elapsed: 55 }), cfg), true);
});

test('reactionTo: starts on a break, ends on its cue-in, ignores the rest', () => {
  const here = { channelId: 'la-1', inBreak: false };
  assert.equal(reactionTo(ev('cue-out', { duration: 30 }), cfg, here), 'start');
  assert.equal(reactionTo(ev('cue-out-cont', { duration: 60, elapsed: 10 }), cfg, here), 'start');
  assert.equal(reactionTo(ev('cue-in'), cfg, here), null);
  assert.equal(reactionTo(ev('cue-in'), cfg, { ...here, inBreak: true }), 'end');
  assert.equal(reactionTo(ev('cue-out', { duration: 30 }), cfg, { ...here, inBreak: true }), null);
  assert.equal(reactionTo(ev('cue-out', { duration: 3 }), cfg, here), null);
  assert.equal(reactionTo(ev('daterange'), cfg, here), null);
  assert.equal(reactionTo(ev('cue-out', { channel: 'antena-3' }), cfg, here), null);
  assert.equal(reactionTo(ev('cue-out'), null, here), null);
});

test('audioTarget: mute and lowering only change what the user has chosen', () => {
  const vol = { v: 0.8, m: false };
  assert.deepEqual(audioTarget(vol, null, true), { v: 0.8, m: false });
  assert.deepEqual(audioTarget(vol, { muted: true }, true), { v: 0.8, m: true });
  assert.deepEqual(audioTarget(vol, { gain: 0.25 }, true), { v: 0.2, m: false });
  assert.equal(audioTarget(vol, null, false).m, true);
  assert.equal(audioTarget({ v: 1, m: true }, { gain: 0.5 }, true).m, true);
});

test('audioTouched tells a change by the user from the reaction\'s own', () => {
  const wanted = { v: 0.2, m: false };
  assert.equal(audioTouched({ v: 0.2, m: false }, wanted), false);
  assert.equal(audioTouched({ v: 0.2000001, m: false }, wanted), false);
  assert.equal(audioTouched({ v: 0.6, m: false }, wanted), true);
  assert.equal(audioTouched({ v: 0.2, m: true }, wanted), true);
});

test('duckedGain stays between 0 and 1', () => {
  assert.equal(duckedGain(25), 0.25);
  assert.equal(duckedGain(150), 1);
  assert.equal(duckedGain(-5), 0);
});

test('altChannel finds by id or by name, and only what can be played', () => {
  const ch = (id, name, extra = {}) => ({ id, name, kind: 'tv', ok: null, sources: [{ u: 'https://s/x.m3u8' }], ...extra });
  const list = [ch('la-2', 'La 2'), ch('cuatro', 'Cuatro', { ok: false }), ch('web', 'Solo web', { sources: [] }), ch('trece', 'Trece')];
  assert.equal(altChannel(list, 'la-2').name, 'La 2');
  assert.equal(altChannel(list, '  LA 2 ').id, 'la-2');
  assert.equal(altChannel(list, 'Trece').id, 'trece');
  assert.equal(altChannel(list, 'Cuatro'), undefined);
  assert.equal(altChannel(list, 'Solo web'), undefined);
  assert.equal(altChannel(list, ''), undefined);
});

test('startText says what is being done', () => {
  assert.equal(startText({ ...cfg }, ''), 'Pausa de anuncios · sonido silenciado');
  assert.equal(startText({ ...cfg, audio: 'lower' }, ''), 'Pausa de anuncios · volumen al 25 %');
  assert.equal(startText({ ...cfg, audio: 'keep', screen: 'channel' }, 'La 2'), 'Pausa de anuncios · viendo La 2');
  assert.equal(startText({ ...cfg, audio: 'keep', screen: 'web' }, ''), 'Pausa de anuncios · mostrando una web');
  assert.equal(startText({ ...cfg, audio: 'keep' }, ''), 'Pausa de anuncios');
});

test('untilMarker: when the segment is unknown, how far the marker is from the player', () => {
  // seen 2 s ago, 6 s before the end of the playlist; the player is 10 s behind the end: 10 - 6 - 2 = 2 s to go
  assert.equal(untilMarker({ lead: 6, ts: 98 }, 10, 100), 2);
  // already played: negative, by how much
  assert.equal(untilMarker({ lead: 20, ts: 100 }, 10, 100), -10);
  assert.equal(untilMarker({ lead: 0, ts: 100 }, 6, 100), 6);
  // not enough to tell
  assert.equal(untilMarker({ ts: 100 }, 10, 100), undefined);
  assert.equal(untilMarker({ lead: 6, ts: 100 }, NaN, 100), undefined);
  assert.equal(untilMarker({ lead: null, ts: 100 }, 10, 100), undefined);
  // a clock that is far off cannot make it wait or fire absurdly
  assert.equal(untilMarker({ lead: 6, ts: 1 }, 10, 100), 10 - 6 - 15);
  assert.equal(untilMarker({ lead: 6, ts: 500 }, 10, 100), 4);
});
