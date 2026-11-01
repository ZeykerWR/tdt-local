// The messages between TDT local and the bridge script (tools/puente-atresplayer) that the user installs in their
// browser and that runs inside Atresplayer's embedded player. Without that script nothing is said and nothing happens.

export const ATRES_ORIGIN = 'https://www.atresplayer.com';

/**
 * What a message from the bridge says: `{kind: 'ready'}`, `{kind: 'ad', on, playing}`, `{kind: 'meter', loudness,
 * gainDb}` (what its leveler hears and does), or `null` for anything else.
 * Only a message sent by the iframe of the tile itself, from Atresplayer's origin, counts.
 * @param {{origin: string, source: unknown, data: unknown}} event
 * @param {unknown} frameWindow - `contentWindow` of the tile's iframe
 */
export function parseBridge(event, frameWindow) {
  if (event.origin !== ATRES_ORIGIN || !frameWindow || event.source !== frameWindow) return null;
  const d = event.data;
  if (!d || typeof d !== 'object' || d.source !== 'tdt-bridge') return null;
  if (d.type === 'ready') return { kind: 'ready' };
  if (d.type === 'state') return { kind: 'ad', on: d.ad === true, playing: d.playing === true };
  if (d.type === 'meter') {
    const number = (v) => (typeof v === 'number' && Number.isFinite(v) ? v : null);
    return { kind: 'meter', loudness: number(d.loudness), gainDb: number(d.gainDb) };
  }
  return null;
}

/** The audio the player inside the iframe should have (the bridge silences it; it never turns it up by itself). */
export function audioMessage({ v, m }) {
  const volume = Number.isFinite(v) ? Math.min(1, Math.max(0, v)) : 1;
  return { source: 'tdt-local', type: 'audio', muted: !!m, volume };
}

/** The leveler and equalizer settings the player inside the iframe should apply (the bridge cleans them up again). */
export function fxMessage({ level, eq }) {
  return {
    source: 'tdt-local',
    type: 'fx',
    level: { on: !!level.on, target: level.target, boost: level.boost },
    eq: { on: !!eq.on, gains: Array.from(eq.gains) },
  };
}

/**
 * How long the player has been showing programme (playing, and not in an ad) when a message arrives. The ad that
 * comes right after pressing «Directo», or after the player starts over, has no programme before it: it is the
 * start-up ad, not a break of the channel.
 */
export class ContentClock {
  constructor() {
    this.since = 0;
  }

  /**
   * Feed it what the bridge said. Returns the seconds of programme that had been playing before this message.
   * @param {{on: boolean, playing: boolean}} state
   * @param {number} now - milliseconds
   */
  update({ on, playing }, now) {
    const before = this.since ? (now - this.since) / 1000 : 0;
    if (playing && !on) {
      if (!this.since) this.since = now;
    } else {
      this.since = 0;
    }
    return before;
  }
}
