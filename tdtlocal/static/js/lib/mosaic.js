// Multi-view bookkeeping: which channel goes into each tile, and which tile gets the audio next.

/**
 * Channel for every empty tile: first what was saved last time, then the channels that follow the active one
 * in the visible list (healthy ones before known-down ones).
 * @param {Array<object|null>} tiles - current channel of each tile, or null
 * @param {{savedIds: Array<string|null>, view: Array, channels: Array, focusId: string|null}} ctx
 * @returns {Array<object|null>} same length as `tiles`; filled where a channel was found
 */
export function fillAssignments(tiles, { savedIds, view, channels, focusId }) {
  const out = tiles.slice();
  const used = new Set(out.filter(Boolean).map((c) => c.id));
  const vi = focusId ? view.findIndex((x) => x.id === focusId) : -1;
  const pool = view.slice(vi + 1).concat(view.slice(0, Math.max(vi + 1, 0))).filter((c) => c.sources.length);
  const queue = pool.filter((c) => c.ok !== false).concat(pool.filter((c) => c.ok === false));
  out.forEach((current, i) => {
    if (current) return;
    let c = channels.find((x) => x.id === savedIds[i] && x.sources.length && !used.has(x.id));
    if (!c) c = queue.find((x) => !used.has(x.id));
    if (c) { out[i] = c; used.add(c.id); }
  });
  return out;
}

/**
 * Tile index that receives the audio after `focus`, skipping empty, stopped or failed tiles.
 * @returns {number} -1 if no other tile has a signal
 */
export function nextRotation(tiles, focus) {
  for (let k = 1; k <= tiles.length; k++) {
    const i = (focus + k) % tiles.length;
    const t = tiles[i];
    if (t.c && t.running && !t.failed) return i;
  }
  return -1;
}
