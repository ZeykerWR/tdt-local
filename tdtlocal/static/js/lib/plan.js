// Which sources to try, and in which order, when a channel is played.

const rank = (s) => (s.ok === true ? 0 : s.ok === null ? 1 : 2);

/**
 * Ordered list of `{u, n, f}` to try: the last source that worked first, then healthy ones,
 * then unknown, then those that failed their last check. Original order breaks ties.
 * @param {object} channel - channel with `sources: [{u, ok, f}]`
 * @param {{pref?: {u: string}, onlyUrl?: string, canPlayFmt?: (f: string) => boolean}} options
 */
export function buildPlan(channel, { pref, onlyUrl, canPlayFmt = () => true } = {}) {
  let order = channel.sources.map((s, i) => ({ ...s, n: i + 1 })).filter((s) => !onlyUrl || s.u === onlyUrl);
  // radio: drop formats this browser cannot play (if none is left, try anyway)
  const usable = order.filter((s) => canPlayFmt(s.f));
  if (usable.length) order = usable;
  const first = (s) => (pref && pref.u === s.u ? -1 : 0);
  order.sort((a, b) => first(a) - first(b) || rank(a) - rank(b) || a.n - b.n);
  return order.map((s) => ({ u: s.u, n: s.n, f: s.f || '' }));
}

/** hls.js for TV and for m3u8 radio; mp3/aac radio goes straight to the media element. */
export const usesHls = (channel, step) => channel.kind !== 'radio' || step.f === 'm3u8' || /\.m3u8?(\?|$)/i.test(step.u);

/** Whether this browser can play a radio format (`audio` is an HTMLMediaElement). */
export function canPlayFormat(audio, f) {
  if (f === 'mp3') return !!audio.canPlayType('audio/mpeg');
  if (f === 'aac') return !!(audio.canPlayType('audio/aac') || audio.canPlayType('audio/aacp'));
  return true;
}
