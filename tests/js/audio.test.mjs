import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  BANDS, EQ_RANGE, MAX_CUT, PRESETS, TAU_DOWN, TAU_UP, TAU_WARM, dbToGain, defaultPrefs, desiredGainDb, effective, formatDb, gainToDb,
  loudness, presetOf, sanitize, smoothPower, sourceLoudness, stepGain, withChannel, withGlobal,
} from '../../tdtlocal/static/js/lib/audio.js';

const near = (a, b, eps = 1e-6) => assert.ok(Math.abs(a - b) < eps, `${a} is not ${b}`);

test('dB and gain convert both ways', () => {
  near(dbToGain(0), 1);
  near(dbToGain(-6.0206), 0.5, 1e-4);
  near(gainToDb(dbToGain(9)), 9);
  assert.equal(gainToDb(0), -Infinity);
});

test('loudness of a full-scale sine and of silence', () => {
  near(loudness(0.5), -0.691 + 10 * Math.log10(0.5));
  assert.equal(loudness(0), -Infinity);
  near(loudness(0.5) - loudness(0.05), 10); // ten times less power is 10 dB less
});

test('the leveler raises what is quiet and lowers what is loud, within limits', () => {
  const level = { target: -20, boost: 12 };
  assert.equal(desiredGainDb(-30, level), 10); // quiet: up
  assert.equal(desiredGainDb(-14, level), -6); // loud: down
  assert.equal(desiredGainDb(-20, level), 0);
  assert.equal(desiredGainDb(-45, level), 12); // very quiet: not more than the boost allows
  assert.equal(desiredGainDb(10, level), -MAX_CUT); // absurdly loud: not more than the cut allows
  assert.equal(desiredGainDb(-30, { target: -20, boost: 4 }), 4);
});

test('silence and noise are not boosted', () => {
  assert.equal(desiredGainDb(-60, { target: -20, boost: 12 }), null);
  assert.equal(desiredGainDb(-Infinity, { target: -20, boost: 12 }), null);
  assert.equal(stepGain(7, null, 1), 7); // and the gain stays where it was
});

test('stepGain falls faster than it rises, and gets there', () => {
  const down = stepGain(0, -10, 0.5);
  const up = stepGain(0, 10, 0.5);
  assert.ok(Math.abs(down) > Math.abs(up));
  near(down, -10 * (1 - Math.exp(-0.5 / TAU_DOWN)));
  near(up, 10 * (1 - Math.exp(-0.5 / TAU_UP)));
  let g = 0;
  for (let i = 0; i < 400; i++) g = stepGain(g, 8, 0.1); // 40 s
  near(g, 8, 0.01);
});

test('smoothPower starts from the first sample and then follows', () => {
  assert.equal(smoothPower(null, 0.3, 0.1, 1), 0.3);
  const next = smoothPower(0.3, 0.9, 0.1, 1);
  assert.ok(next > 0.3 && next < 0.9);
  near(smoothPower(0.3, 0.9, 100, 1), 0.9, 1e-6);
});

test('the leveler converges on the target from a quiet and from a loud start', () => {
  const level = { target: -20, boost: 12 };
  for (const input of [-31, -12]) {
    let power = null;
    let gain = 0;
    for (let i = 0; i < 600; i++) {
      power = smoothPower(power, dbToGain(input + 0.691) ** 2, 0.1, 0.5);
      gain = stepGain(gain, desiredGainDb(loudness(power), level), 0.1);
    }
    near(input + gain, -20, 0.05);
  }
});

test('sanitize repairs anything', () => {
  assert.deepEqual(sanitize(null), defaultPrefs());
  assert.deepEqual(sanitize('x'), defaultPrefs());
  const p = sanitize({
    global: { level: { on: true, target: -99, boost: 99 }, eq: { on: true, gains: [50, -50, 'x', null, 3] } },
    channels: { a: { level: { on: true, target: -18, boost: 6 }, junk: 1 }, b: 5, c: {}, d: { eq: { on: true, gains: [1] } } },
  });
  assert.deepEqual(p.global.level, { on: true, target: -40, boost: 24 });
  assert.equal(p.global.eq.gains.length, BANDS.length);
  assert.deepEqual(p.global.eq.gains.slice(0, 5), [EQ_RANGE, -EQ_RANGE, 0, 0, 3]);
  assert.deepEqual(Object.keys(p.channels).sort(), ['a', 'd']);
  assert.equal(p.channels.a.eq, undefined);
  assert.equal(p.channels.d.eq.gains[0], 1);
});

test('a channel uses its own settings, and the global ones for what it does not override', () => {
  let prefs = defaultPrefs();
  prefs = withGlobal(prefs, 'level', { on: true, target: -22, boost: 10 });
  prefs = withChannel(prefs, 'la-1', 'eq', { on: true, gains: PRESETS.voice.gains });
  const la1 = effective(prefs, 'la-1');
  assert.equal(la1.level.target, -22);
  assert.equal(la1.ownLevel, false);
  assert.equal(la1.ownEq, true);
  assert.deepEqual(la1.eq.gains, PRESETS.voice.gains);
  const other = effective(prefs, 'antena-3');
  assert.equal(other.ownEq, false);
  assert.equal(other.eq.on, false);
  assert.equal(effective(prefs, undefined).ownEq, false);
});

test('withChannel and withGlobal never change what they are given, and null gives the channel back to the global', () => {
  const prefs = defaultPrefs();
  const copy = JSON.stringify(prefs);
  const a = withChannel(prefs, 'x', 'level', { on: true, target: -18, boost: 6 });
  assert.equal(JSON.stringify(prefs), copy);
  assert.ok(a.channels.x);
  const b = withChannel(a, 'x', 'level', null);
  assert.deepEqual(b.channels, {});
  const c = withChannel(withChannel(a, 'x', 'eq', defaultPrefs().global.eq), 'x', 'level', null);
  assert.deepEqual(Object.keys(c.channels.x), ['eq']);
  withGlobal(prefs, 'eq', { on: true, gains: PRESETS.bass.gains });
  assert.equal(JSON.stringify(prefs), copy);
});

test('presetOf names a preset by its gains', () => {
  assert.equal(presetOf(PRESETS.voice.gains), 'voice');
  assert.equal(presetOf(PRESETS.flat.gains), 'flat');
  assert.equal(presetOf([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]), '');
  for (const preset of Object.values(PRESETS)) assert.equal(preset.gains.length, BANDS.length);
});

test('formatDb', () => {
  assert.equal(formatDb(7.04), '+7 dB');
  assert.equal(formatDb(-6.26), '−6,3 dB');
  assert.equal(formatDb(0), '0 dB');
  assert.equal(formatDb(-0.02), '0 dB');
  assert.equal(formatDb(4.5), '+4,5 dB');
  assert.equal(formatDb(NaN), '—');
});

test('a new channel adapts quickly at first, and a loud one is always lowered quickly', () => {
  assert.ok(stepGain(0, 10, 0.5, true) > stepGain(0, 10, 0.5, false));
  near(stepGain(0, 10, 0.5, true), 10 * (1 - Math.exp(-0.5 / TAU_WARM)));
  near(stepGain(0, -10, 0.5, true), stepGain(0, -10, 0.5, false));
});

test('sourceLoudness undoes the volume control', () => {
  const full = sourceLoudness(0.01, 1);
  near(sourceLoudness(0.01 * 0.25 * 0.25, 0.25), full);
  assert.equal(sourceLoudness(0.01, 0), -Infinity);
  assert.equal(sourceLoudness(0.01, 0.005), -Infinity);
  assert.equal(sourceLoudness(0, 1), -Infinity);
});
