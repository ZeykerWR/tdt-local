// Application state shared by the page's modules, plus the preferences restored from localStorage.
import { ROTATION_SECS } from './lib/commands.js';
import { epgLine } from './lib/epg.js';
import { store } from './store.js';

export const TILES = 4;

const vol = store.get('vol', null);
const secs = store.get('rotSecs', 20);
const alerts = store.get('alerts', {});
const savedKind = store.get('kind', 'tv');
const kind = savedKind === 'radio' || savedKind === 'u7d' ? savedKind : 'tv';
const cats = store.get('cats', {}); // list kind -> last category chosen

export const state = {
  channels: [], // every channel of both lists (TV, radio, own)
  view: [], // the ones that pass the filters, in list order
  byId: new Map(),
  tiles: [],
  focus: 0, // active tile: the one with the audio
  mode: 'single', // 'single' | 'multi'
  layout: store.get('layout', 'mosaic') === 'focus' ? 'focus' : 'mosaic',
  rot: { on: store.get('rotOn', false) === true, secs: ROTATION_SECS.includes(secs) ? secs : 20, hold: false },
  vol: { v: vol && typeof vol.v === 'number' ? vol.v : 1, m: !!(vol && vol.m) },
  meta: null,
  health: null,
  signature: '',
  checkTimer: null,
  kind,
  u7d: null, // U7D: the channel opened and its programmes ({c, items, error}), or null while choosing a channel
  cats,
  cat: cats[kind] || (kind === 'tv' ? store.get('cat', '') : ''),
  grp: '',
  favs: new Set(store.get('favs', [])),
  prefs: store.get('prefs', {}), // channel id -> {u}: the source that worked last time
  epg: { now: {}, updated: null }, // epg id -> [[start, end, title], ...] (now and next)
  stt: { on: store.get('sttOn', false) === true }, // subtitles of the active tile
  alerts: {
    words: Array.isArray(alerts.words) ? alerts.words : [],
    on: alerts.on === true,
    jump: alerts.jump !== false,
  },
};

export const focusTile = () => state.tiles[state.focus];
export const cur = () => focusTile().c;

export const nowTs = () => Date.now() / 1000;

/** Upcoming programmes the server sent for a channel, or undefined. */
export const epgEntries = (c) => (c && c.epg ? state.epg.now[c.epg] : undefined);

/** One-line "now / next" summary of a channel. */
export const channelEpgLine = (c) => epgLine(epgEntries(c), nowTs());
