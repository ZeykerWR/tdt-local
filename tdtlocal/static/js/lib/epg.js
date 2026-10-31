// "Now / next" on top of the programme lists the server sends: [[start, end, title], ...].
import { hhmm } from './format.js';

/**
 * What is on now (`cur`) and next (`next`) in a list of upcoming programmes.
 * The server sends three, so a change of programme shows up without waiting for the next poll.
 * @returns {{cur: Array|null, next: Array|null} | null}
 */
export function epgOf(entries, nowSec) {
  if (!entries) return null;
  const i = entries.findIndex((p) => p[1] > nowSec);
  if (i < 0) return null;
  return entries[i][0] <= nowSec
    ? { cur: entries[i], next: entries[i + 1] || null }
    : { cur: null, next: entries[i] };
}

/** One-line summary for lists and tile bars: the current title, or "20:30 · title" for what comes next. */
export function epgLine(entries, nowSec) {
  const e = epgOf(entries, nowSec);
  if (!e) return '';
  return e.cur ? e.cur[2] : hhmm(e.next[0]) + ' · ' + e.next[2];
}

/** Percentage (0-100) of the current programme already broadcast. */
export function progress(cur, nowSec) {
  return Math.min(100, Math.max(0, ((nowSec - cur[0]) / (cur[1] - cur[0])) * 100));
}

/** Lines shown under the channel name: now, then next. */
export function epgDetail(entries, nowSec) {
  const e = epgOf(entries, nowSec);
  if (!e) return [];
  const lines = [];
  if (e.cur) lines.push('Ahora: ' + e.cur[2] + ' (' + hhmm(e.cur[0]) + '–' + hhmm(e.cur[1]) + ')');
  if (e.cur && e.next) lines.push('Después (' + hhmm(e.next[0]) + '): ' + e.next[2]);
  if (!e.cur) lines.push('A las ' + hhmm(e.next[0]) + ': ' + e.next[2]);
  return lines;
}
