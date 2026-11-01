// GENERADO por scripts/build_bridge.py a partir de tdtlocal/static/js/lib/audio.js y
// tdtlocal/static/js/audio.js.
// No lo edites: cambia esos archivos y vuelve a ejecutar el script. Es la cadena de sonido de TDT local (igualador
// de volumen y ecualizador) empaquetada como un script normal, para que la extensión del puente la use dentro del
// reproductor.
(function () {
'use strict';
// Sound: the settings of the volume leveler and the equalizer (global, with an override per channel) and the maths
// the leveler uses, as pure functions. audio.js builds the Web Audio graph from them.

/** Centre frequencies of the equalizer (Hz). The first is a low shelf, the last a high shelf, the rest peak. */
const BANDS = [31, 62, 125, 250, 500, 1000, 2000, 4000, 8000, 16000];
const EQ_RANGE = 12; // dB, either way
const MAX_CUT = 24; // dB the leveler may lower a loud signal
const GATE = -50; // loudness below this is silence or noise: the leveler leaves its gain as it is
const MAX_CHANNELS = 500;

const PRESETS = {
  flat: { label: 'Plano', gains: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0] },
  voice: { label: 'Voz clara', gains: [-6, -4, -2, 0, 1, 3, 4, 3, 1, 0] },
  bass: { label: 'Graves', gains: [6, 5, 3, 1, 0, 0, 0, 0, 0, 0] },
  treble: { label: 'Agudos', gains: [0, 0, 0, 0, 0, 0, 1, 3, 5, 6] },
  smile: { label: 'En V', gains: [5, 4, 2, 0, -2, -2, 0, 2, 4, 5] },
  night: { label: 'Noche (sin graves)', gains: [-9, -7, -4, -1, 0, 1, 1, 0, 0, 0] },
};

const defaultLevel = () => ({ on: false, target: -20, boost: 12 });
const defaultEq = () => ({ on: false, gains: PRESETS.flat.gains.slice() });
const defaultPrefs = () => ({ global: { level: defaultLevel(), eq: defaultEq() }, channels: {} });

const clamp = (n, lo, hi) => Math.min(hi, Math.max(lo, n));
const num = (v, fallback) => (typeof v === 'number' && Number.isFinite(v) ? v : fallback);

function cleanLevel(raw) {
  const d = defaultLevel();
  const r = raw && typeof raw === 'object' ? raw : {};
  return { on: r.on === true, target: clamp(num(r.target, d.target), -40, -6), boost: clamp(num(r.boost, d.boost), 0, 24) };
}

function cleanEq(raw) {
  const r = raw && typeof raw === 'object' ? raw : {};
  const gains = BANDS.map((_, i) => clamp(num(Array.isArray(r.gains) ? r.gains[i] : 0, 0), -EQ_RANGE, EQ_RANGE));
  return { on: r.on === true, gains };
}

/** Whatever was stored, turned into well-formed preferences (it may be old, hand-edited or damaged). */
function sanitize(raw) {
  const r = raw && typeof raw === 'object' ? raw : {};
  const g = r.global && typeof r.global === 'object' ? r.global : {};
  const out = { global: { level: cleanLevel(g.level), eq: cleanEq(g.eq) }, channels: {} };
  const channels = r.channels && typeof r.channels === 'object' ? r.channels : {};
  for (const [id, own] of Object.entries(channels).slice(0, MAX_CHANNELS)) {
    if (!own || typeof own !== 'object') continue;
    const entry = {};
    if (own.level) entry.level = cleanLevel(own.level);
    if (own.eq) entry.eq = cleanEq(own.eq);
    if (entry.level || entry.eq) out.channels[id] = entry;
  }
  return out;
}

/**
 * What applies to a channel: its own leveler and equalizer settings where it has them, the global ones where not.
 * @returns {{level: object, eq: object, ownLevel: boolean, ownEq: boolean}}
 */
function effective(prefs, id) {
  const own = (id && prefs.channels[id]) || {};
  return {
    level: own.level || prefs.global.level,
    eq: own.eq || prefs.global.eq,
    ownLevel: !!own.level,
    ownEq: !!own.eq,
  };
}

/**
 * Preferences with one part (`'level'` or `'eq'`) of one channel replaced; `null` removes the channel's own value,
 * so the global one applies again. Never changes what it is given.
 */
function withChannel(prefs, id, part, value) {
  const channels = { ...prefs.channels };
  const entry = { ...(channels[id] || {}) };
  if (value) entry[part] = value; else delete entry[part];
  if (entry.level || entry.eq) channels[id] = entry; else delete channels[id];
  return { ...prefs, channels };
}

const withGlobal = (prefs, part, value) => ({ ...prefs, global: { ...prefs.global, [part]: value } });

/** The preset whose gains these are, or `''`. */
function presetOf(gains) {
  const found = Object.entries(PRESETS).find(([, p]) => p.gains.every((g, i) => g === gains[i]));
  return found ? found[0] : '';
}

const dbToGain = (db) => 10 ** (db / 20);
const gainToDb = (gain) => (gain > 0 ? 20 * Math.log10(gain) : -Infinity);

/** Loudness (in the scale of LUFS) of a signal from the mean square of its K-weighted samples. */
const loudness = (meanSquare) => (meanSquare > 0 ? -0.691 + 10 * Math.log10(meanSquare) : -Infinity);

/** Smooth a power measurement: `tau` seconds is how long it takes to follow a change. */
const smoothPower = (previous, sample, dt, tau) => (previous === null ? sample : previous + (sample - previous) * (1 - Math.exp(-dt / tau)));

/**
 * The gain, in dB, that brings a signal of this loudness to the target, within what the leveler may do.
 * `null` when there is nothing to measure (silence): the gain should stay where it is.
 */
function desiredGainDb(measured, { target, boost }) {
  if (!Number.isFinite(measured) || measured < GATE) return null;
  return clamp(target - measured, -MAX_CUT, boost);
}

/** Time the gain takes to follow: quickly down when something loud arrives, slowly up so it does not pump. */
const TAU_DOWN = 0.4;
const TAU_UP = 4;
/** On a new channel the first seconds of sound adapt quickly in both directions. */
const WARM_SECONDS = 3;
const TAU_WARM = 0.8;

/** One step of the leveler's gain (dB) towards `desired`, `dt` seconds later. `warm`: just started on a channel. */
function stepGain(current, desired, dt, warm = false) {
  if (desired === null) return current;
  const tau = desired < current ? TAU_DOWN : warm ? TAU_WARM : TAU_UP;
  return current + (desired - current) * (1 - Math.exp(-dt / tau));
}

/**
 * Loudness of what a channel carries, from the power measured after the volume control: undoes that volume, so
 * that turning it down does not make the leveler think the channel got quieter. `-Infinity` when there is nothing
 * to measure (silence, or a volume too low to tell).
 */
function sourceLoudness(meanSquare, volume) {
  if (!(volume > 0.01) || !(meanSquare > 0)) return -Infinity;
  return loudness(meanSquare / (volume * volume));
}

/** "−7 dB", "+4,5 dB": a gain for people (Spanish decimal comma, real minus sign). */
function formatDb(db) {
  if (!Number.isFinite(db)) return '—';
  const text = (Math.round(db * 10) / 10).toFixed(1).replace('.', ',').replace(/,0$/, '');
  return (db > 0.04 ? '+' : db < -0.04 ? '−' : '') + text.replace('-', '') + ' dB';
}

// The sound chain of a tile, built with the Web Audio API: volume leveler -> equalizer -> limiter.
// What the settings are, and the leveler's maths, is in lib/audio.js.
//
//   <video> -> level (gain) -> 10 filters (EQ) -> limiter -> speakers
//      \
//       +-> K-weighting -> analyser   (measures the signal; the leveler sets `level` from it)
//
// The <video> keeps its own volume and mute: they apply before the chain, so everything else in the page keeps
// working as it did, and the measurement undoes the volume (see sourceLoudness).

const TICK_MS = 100;
const FFT = 4096; // about 85 ms of sound: a tick every 100 ms sees nearly all of it
const POWER_TAU = 0.5; // seconds the loudness measurement takes to follow a change
const RAMP = 0.05; // seconds to move a gain to its new value, so there are no clicks
// A DynamicsCompressorNode adds a fixed "makeup" gain that grows with its ratio; with ours (20:1 at -1.5 dB) it is
// 0.89 dB, measured. It is taken back, so that turning the processing on does not change the volume.
const MAKEUP_DB = -0.89;

let ctx = null;
let timer = 0;
const chains = new Set();
const byVideo = new WeakMap();
const wakeHooks = new Set();

const AudioContextClass = window.AudioContext || window.webkitAudioContext;

const audioSupported = () => !!AudioContextClass;

function context() {
  if (!ctx && AudioContextClass) {
    ctx = new AudioContextClass({ latencyHint: 'playback' });
    ctx.addEventListener('statechange', () => { if (ctx.state === 'running') for (const hook of wakeHooks) hook(); });
  }
  return ctx;
}

/** The context can make sound. Browsers keep it suspended until the page has had a click or a key press. */
const awake = () => !!ctx && ctx.state === 'running';

/** Try to start the context (it needs a user gesture in most browsers). */
async function wake() {
  const c = context();
  if (!c) return false;
  if (c.state !== 'running') {
    try { await c.resume(); } catch { /* not allowed yet */ }
  }
  return c.state === 'running';
}

/** `hook` is called whenever the context starts running. Until then no <video> is routed through it. */
function onWake(hook) {
  wakeHooks.add(hook);
  const gesture = () => { wake(); };
  for (const type of ['pointerdown', 'keydown']) document.addEventListener(type, gesture, { capture: true, passive: true });
  wake(); // some browsers allow it already
}

function tick() {
  const now = performance.now();
  for (const chain of chains) chain.measure(now);
}

class Chain {
  /** @param {HTMLMediaElement} video */
  constructor(video) {
    const c = context();
    this.video = video;
    this.source = c.createMediaElementSource(video);

    // measurement: K-weighting (a high shelf and a high-pass, as in ITU-R BS.1770) into an analyser
    const shelf = c.createBiquadFilter();
    shelf.type = 'highshelf';
    shelf.frequency.value = 1681;
    shelf.gain.value = 4;
    const rlb = c.createBiquadFilter();
    rlb.type = 'highpass';
    rlb.frequency.value = 38;
    rlb.Q.value = 0.5;
    this.analyser = c.createAnalyser();
    this.analyser.fftSize = FFT;
    this.analyser.smoothingTimeConstant = 0;
    this.samples = new Float32Array(FFT);
    const sink = c.createGain(); // an analyser with nothing after it may not be processed in every browser
    sink.gain.value = 0;
    this.source.connect(shelf).connect(rlb).connect(this.analyser).connect(sink).connect(c.destination);

    // sound path
    this.level = c.createGain();
    this.filters = BANDS.map((freq, i) => {
      const f = c.createBiquadFilter();
      f.type = i === 0 ? 'lowshelf' : i === BANDS.length - 1 ? 'highshelf' : 'peaking';
      f.frequency.value = freq;
      f.Q.value = 1.41;
      f.gain.value = 0;
      return f;
    });
    this.limiter = c.createDynamicsCompressor();
    this.limiter.threshold.value = 0;
    this.limiter.knee.value = 0;
    this.limiter.ratio.value = 1;
    this.limiter.attack.value = 0.003;
    this.limiter.release.value = 0.12;
    this.trim = c.createGain();
    this.source.connect(this.level);
    let node = this.level;
    for (const f of this.filters) node = node.connect(f);
    node.connect(this.limiter).connect(this.trim).connect(c.destination);

    this.fx = null;
    this.reset();
    this.last = performance.now();
    chains.add(this);
    if (!timer) timer = setInterval(tick, TICK_MS);
  }

  /** New channel: forget what was measured and adapt quickly to the new one. */
  reset() {
    this.power = null;
    this.gainDb = 0;
    this.measured = -Infinity;
    this.warm = WARM_SECONDS;
    if (this.fx) this.level.gain.setTargetAtTime(1, ctx.currentTime, RAMP);
  }

  /** @param {{level: {on: boolean, target: number, boost: number}, eq: {on: boolean, gains: number[]}}} fx */
  configure(fx) {
    this.fx = fx;
    const t = ctx.currentTime;
    this.filters.forEach((f, i) => f.gain.setTargetAtTime(fx.eq.on ? fx.eq.gains[i] : 0, t, RAMP));
    const guard = fx.level.on || fx.eq.on; // the limiter only guards against what the chain could add
    this.limiter.ratio.value = guard ? 20 : 1;
    this.limiter.threshold.value = guard ? -1.5 : 0;
    this.trim.gain.setTargetAtTime(guard ? dbToGain(MAKEUP_DB) : 1, t, RAMP);
    if (!fx.level.on) {
      this.gainDb = 0;
      this.level.gain.setTargetAtTime(1, t, RAMP);
    }
  }

  /** Called every tick: measure, and if the leveler is on, move the gain. */
  measure(now) {
    const dt = Math.min(5, Math.max(0.001, (now - this.last) / 1000));
    this.last = now;
    this.analyser.getFloatTimeDomainData(this.samples);
    let sum = 0;
    for (const x of this.samples) sum += x * x;
    const power = sum / this.samples.length;
    const volume = this.video.muted ? 0 : this.video.volume;
    if (power > 0 && volume > 0.01) {
      this.power = smoothPower(this.power, power, dt, POWER_TAU);
      this.measured = sourceLoudness(this.power, volume);
    } else if (power === 0) {
      this.power = null; // true silence: the next sound is measured afresh
      this.measured = -Infinity;
    }
    if (!this.fx || !this.fx.level.on) return;
    const desired = desiredGainDb(this.measured, this.fx.level);
    if (desired !== null && this.warm > 0) this.warm -= dt;
    this.gainDb = stepGain(this.gainDb, desired, dt, this.warm > 0);
    this.level.gain.setTargetAtTime(dbToGain(this.gainDb), ctx.currentTime, RAMP);
  }

  /** What the dialog shows: the loudness of the channel (as it comes) and what the leveler does to it. */
  readout() {
    return { loudness: this.measured, gainDb: this.fx && this.fx.level.on ? this.gainDb : 0, gain: gainToDb(this.level.gain.value) };
  }
}

/**
 * The chain of a <video>, made the first time it is asked for. `null` while the context is not running: a
 * <video> routed through a suspended context would be silent, and it cannot be taken out again.
 * @param {HTMLMediaElement} video
 * @returns {Chain | null}
 */
function chainFor(video) {
  const known = byVideo.get(video);
  if (known) return known;
  if (!awake()) return null;
  try {
    const chain = new Chain(video);
    byVideo.set(video, chain);
    return chain;
  } catch {
    return null;
  }
}

globalThis.TDT_AUDIO = { chainFor, wake, awake, audioSupported, sanitize };
}());
