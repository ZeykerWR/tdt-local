// Sound: the settings of the volume leveler and the equalizer (global, with an override per channel) and the maths
// the leveler uses, as pure functions. audio.js builds the Web Audio graph from them.

/** Centre frequencies of the equalizer (Hz). The first is a low shelf, the last a high shelf, the rest peak. */
export const BANDS = [31, 62, 125, 250, 500, 1000, 2000, 4000, 8000, 16000];
export const EQ_RANGE = 12; // dB, either way
export const MAX_CUT = 24; // dB the leveler may lower a loud signal
export const GATE = -50; // loudness below this is silence or noise: the leveler leaves its gain as it is
export const MAX_CHANNELS = 500;

export const PRESETS = {
  flat: { label: 'Plano', gains: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0] },
  voice: { label: 'Voz clara', gains: [-6, -4, -2, 0, 1, 3, 4, 3, 1, 0] },
  bass: { label: 'Graves', gains: [6, 5, 3, 1, 0, 0, 0, 0, 0, 0] },
  treble: { label: 'Agudos', gains: [0, 0, 0, 0, 0, 0, 1, 3, 5, 6] },
  smile: { label: 'En V', gains: [5, 4, 2, 0, -2, -2, 0, 2, 4, 5] },
  night: { label: 'Noche (sin graves)', gains: [-9, -7, -4, -1, 0, 1, 1, 0, 0, 0] },
};

export const defaultLevel = () => ({ on: false, target: -20, boost: 12 });
export const defaultEq = () => ({ on: false, gains: PRESETS.flat.gains.slice() });
export const defaultPrefs = () => ({ global: { level: defaultLevel(), eq: defaultEq() }, channels: {} });

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
export function sanitize(raw) {
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
export function effective(prefs, id) {
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
export function withChannel(prefs, id, part, value) {
  const channels = { ...prefs.channels };
  const entry = { ...(channels[id] || {}) };
  if (value) entry[part] = value; else delete entry[part];
  if (entry.level || entry.eq) channels[id] = entry; else delete channels[id];
  return { ...prefs, channels };
}

export const withGlobal = (prefs, part, value) => ({ ...prefs, global: { ...prefs.global, [part]: value } });

/** The preset whose gains these are, or `''`. */
export function presetOf(gains) {
  const found = Object.entries(PRESETS).find(([, p]) => p.gains.every((g, i) => g === gains[i]));
  return found ? found[0] : '';
}

export const dbToGain = (db) => 10 ** (db / 20);
export const gainToDb = (gain) => (gain > 0 ? 20 * Math.log10(gain) : -Infinity);

/** Loudness (in the scale of LUFS) of a signal from the mean square of its K-weighted samples. */
export const loudness = (meanSquare) => (meanSquare > 0 ? -0.691 + 10 * Math.log10(meanSquare) : -Infinity);

/** Smooth a power measurement: `tau` seconds is how long it takes to follow a change. */
export const smoothPower = (previous, sample, dt, tau) => (previous === null ? sample : previous + (sample - previous) * (1 - Math.exp(-dt / tau)));

/**
 * The gain, in dB, that brings a signal of this loudness to the target, within what the leveler may do.
 * `null` when there is nothing to measure (silence): the gain should stay where it is.
 */
export function desiredGainDb(measured, { target, boost }) {
  if (!Number.isFinite(measured) || measured < GATE) return null;
  return clamp(target - measured, -MAX_CUT, boost);
}

/** Time the gain takes to follow: quickly down when something loud arrives, slowly up so it does not pump. */
export const TAU_DOWN = 0.4;
export const TAU_UP = 4;
/** On a new channel the first seconds of sound adapt quickly in both directions. */
export const WARM_SECONDS = 3;
export const TAU_WARM = 0.8;

/** One step of the leveler's gain (dB) towards `desired`, `dt` seconds later. `warm`: just started on a channel. */
export function stepGain(current, desired, dt, warm = false) {
  if (desired === null) return current;
  const tau = desired < current ? TAU_DOWN : warm ? TAU_WARM : TAU_UP;
  return current + (desired - current) * (1 - Math.exp(-dt / tau));
}

/**
 * Loudness of what a channel carries, from the power measured after the volume control: undoes that volume, so
 * that turning it down does not make the leveler think the channel got quieter. `-Infinity` when there is nothing
 * to measure (silence, or a volume too low to tell).
 */
export function sourceLoudness(meanSquare, volume) {
  if (!(volume > 0.01) || !(meanSquare > 0)) return -Infinity;
  return loudness(meanSquare / (volume * volume));
}

/** "−7 dB", "+4,5 dB": a gain for people (Spanish decimal comma, real minus sign). */
export function formatDb(db) {
  if (!Number.isFinite(db)) return '—';
  const text = (Math.round(db * 10) / 10).toFixed(1).replace('.', ',').replace(/,0$/, '');
  return (db > 0.04 ? '+' : db < -0.04 ? '−' : '') + text.replace('-', '') + ' dB';
}
