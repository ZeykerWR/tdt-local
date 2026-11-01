// Assistant commands that need no model: "pon La 2", "pon La 2, TRECE y El Toro en multivisión rotando cada 30 s".
import { slug } from './text.js';

export const ROTATION_SECS = [10, 15, 20, 30, 45, 60];

const ARTICLE = /^(la|el|los|las) /;

/** The allowed rotation interval closest to `seconds`. */
export const nearestSecs = (seconds) => ROTATION_SECS.reduce((a, b) => (Math.abs(b - seconds) < Math.abs(a - seconds) ? b : a));

/**
 * Channel whose name matches `name` (exact, with or without article, or the shortest name that starts with it).
 * Playable channels of the current list `kind` win over the other list.
 */
export function findChannel(channels, kind, name) {
  const pool = channels.filter((c) => c.sources.length && c.ok !== false && c.kind !== 'u7d');
  const pick = (arr) => arr.find((c) => c.kind === kind) || arr[0];
  const full = slug(name);
  // «la 2» is a name; so is «la sexta»; but «el canal trece» is «trece»: try with and without the article
  for (const n of [full, full.replace(ARTICLE, '')]) {
    if (!n) continue;
    const exact = pool.filter((c) => slug(c.name) === n);
    if (exact.length) return pick(exact);
  }
  const n = full.replace(ARTICLE, '');
  if (n.length < 4) return null;
  const starts = pool.filter((c) => { const s = slug(c.name); return s.startsWith(full) || s.startsWith(n); })
    .sort((a, b) => a.name.length - b.name.length);
  return starts.length ? pick(starts.filter((c) => c.name.length === starts[0].name.length)) : null;
}

/**
 * Parse a command typed to the assistant.
 * @returns {Array<object>|null} actions (`kind`, `play`, `multi`) or `null` if it is not a known command
 */
export function quickCommand(text, channels, kind, maxTiles = 4) {
  const t = text.trim();
  if (/^(la )?(radio|emisoras)$/i.test(t)) return [{ do: 'kind', kind: 'radio' }];
  if (/^(la )?(tele|televisi[oó]n|tv)$/i.test(t)) return [{ do: 'kind', kind: 'tv' }];
  const m = /^(?:pon(?:me)?|ver|ve a|reproduce|sintoniza|abre)\s+(?:el canal\s+)?(.+)$/i.exec(t);
  if (!m) return null;
  let rest = m[1];
  let rotate = null;
  const rot = /\s*,?\s*(?:rotando|rota|rotar)(?: el audio)?(?: cada)?\s+(\d+)\s*(?:s|seg\w*)?\s*$/i.exec(rest);
  if (rot) { rotate = Number(rot[1]); rest = rest.slice(0, rot.index); }
  const multi = /\s*(?:,|\s)?\s*(?:en|con)\s+(?:la\s+)?(?:multivisi[oó]n|mosaico)\s*$/i.exec(rest);
  if (multi) rest = rest.slice(0, multi.index);
  const names = rest.split(/\s*(?:,|\by\b|\be\b|\+)\s*/i).filter(Boolean);
  const found = names.map((n) => findChannel(channels, kind, n));
  if (!found.length || found.some((c) => !c)) return null;
  if (found.length > 1 || multi) return [{ do: 'multi', ids: found.slice(0, maxTiles).map((c) => c.id), rotate }];
  return [{ do: 'play', id: found[0].id }];
}
