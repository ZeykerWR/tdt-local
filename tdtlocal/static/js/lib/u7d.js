// U7D ("últimos 7 días"): channels with catch-up and what each one broadcast recently.

import { atresVideoLink } from './embeds.js';
import { hhmm } from './format.js';

export const U7D_PREFIX = 'u7d:';

/** `{key, ref}` of a programme source (`u7d:la-1:17281881`), or `null` if `u` is not one. */
export function parseU7d(u) {
  if (!u || !u.startsWith(U7D_PREFIX)) return null;
  const i = u.indexOf(':', U7D_PREFIX.length);
  return i < 0 ? null : { key: u.slice(U7D_PREFIX.length, i), ref: u.slice(i + 1) };
}

/**
 * A channel the tile can play for one programme of a U7D channel.
 * @param {{id: string, logo?: string}} chan - entry of the U7D list (`id` is `u7d-<key>`)
 * @param {{id: string, title: string, subtitle?: string, ts: number, image?: string}} item
 */
export function programmeChannel(chan, item) {
  const key = chan.id.replace(/^u7d-/, '');
  const u = U7D_PREFIX + key + ':' + item.id;
  return {
    id: u, name: item.title, kind: 'tv', category: 'Últimos 7 días', group: '', ok: null, vod: true,
    logo: item.image || chan.logo || '', thumb: !!item.image, epg: '', web: '', tags: [], sources: [{ u, ok: null, f: '' }],
  };
}

// Atresmedia's channels have their catch-up on public pages of atresplayer.com (`/<slug>/u7d/`), which only a browser can
// read: the desktop app opens one in its own window and its plugin «atresplayer-u7d» reads the programmes from it.
export const ATRES_PLUGIN = 'atresplayer-u7d';
export const ATRES_CHANNELS = [
  { slug: 'antena3', name: 'Antena 3', logoId: 'antena3' },
  { slug: 'lasexta', name: 'laSexta', logoId: 'lasexta' },
  { slug: 'neox', name: 'Neox', logoId: 'neox' },
  { slug: 'nova', name: 'Nova', logoId: 'nova' },
  { slug: 'mega', name: 'Mega', logoId: 'mega' },
  { slug: 'atreseries', name: 'Atreseries', logoId: 'atreseries' },
];

/** U7D list entries of the Atresmedia channels, with the logo of their live channel. Only the desktop app can read them. */
export function atresChannels(live) {
  const byId = new Map(live.map((c) => [c.id, c]));
  return ATRES_CHANNELS.map((a) => {
    const base = byId.get(a.logoId) || {};
    return {
      id: 'u7d-atres-' + a.slug, name: a.name, kind: 'u7d', provider: 'atres', slug: a.slug, category: 'Últimos 7 días',
      group: '', sources: [], web: '', logo: base.logo || '', epg: '', tags: [], ok: null,
    };
  });
}

/**
 * When a programme of Atresplayer's page started: the page says «Domingo 25», «22:10» and nothing else, so the day of the
 * month is placed in the last 31 days (the page shows a week). 0 if it does not say.
 */
export function atresTs(day, time, now = new Date()) {
  const m = /^(\d{1,2}):(\d{2})$/.exec(time || '');
  if (!day || day < 1 || day > 31 || !m) return 0;
  for (let back = 0; back <= 31; back++) {
    const d = new Date(now.getFullYear(), now.getMonth(), now.getDate() - back, Number(m[1]), Number(m[2]));
    if (d.getDate() === day && d.getTime() <= now.getTime() + 60000) return Math.floor(d.getTime() / 1000);
  }
  return 0;
}

/** The programmes the plugin read, as list items (the same as the ones the server sends for RTVE). */
export function atresItems(read, now = new Date()) {
  return read.map((it) => ({
    id: it.id, title: it.title, subtitle: '', ts: atresTs(it.day, it.time, now), image: it.image || '',
  }));
}

/**
 * The entry for a recording of Atresplayer. Its embedded player does not play recordings (its own request for them,
 * `player/v1/video/<id>`, answers 404): the tile sends the user to the recording's page on atresplayer.com instead.
 */
export function atresProgramme(chan, item) {
  const u = atresVideoLink(item.id);
  return {
    id: u, name: item.title, kind: 'tv', category: 'Últimos 7 días', group: '', ok: null, vod: true, recording: true,
    logo: item.image || chan.logo || '', thumb: !!item.image, epg: '',
    web: 'https://www.atresplayer.com/grabaciones/' + chan.slug + '/' + item.id + '/', tags: [],
    sources: [{ u, ok: null, f: '' }],
  };
}

/** "Hoy · 17:40", "Ayer · 21:30" or "lun 26 oct · 21:30" for a timestamp in seconds. */
export function whenLabel(ts, now = new Date()) {
  if (!ts) return '';
  const d = new Date(ts * 1000);
  const midnight = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const diff = Math.round((midnight(d) - midnight(now)) / 86400000);
  const day = diff === 0 ? 'Hoy' : diff === -1 ? 'Ayer'
    : d.toLocaleDateString('es-ES', { weekday: 'short', day: 'numeric', month: 'short' }).replace(/\./g, '');
  return day + ' · ' + hhmm(ts);
}

/** Newest first (the server already sends it so; this keeps the page right if it ever does not). */
export const newestFirst = (items) => [...items].sort((a, b) => b.ts - a.ts);
