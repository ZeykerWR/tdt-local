// The «Explorar Atresplayer» window: it opens the public «Emitido en TV (U7D)» page of a channel so that the plugin
// «atresplayer-u7d» can read the recordings from it. This module knows nothing about Electron: it says which channels
// and addresses are allowed and cleans what the plugin reports (a page can send the same messages, so nothing is trusted).

export const PLUGIN_ID = 'atresplayer-u7d';
export const SLUGS = ['antena3', 'lasexta', 'neox', 'nova', 'mega', 'atreseries'];
export const HOSTS = ['www.atresplayer.com', 'atresplayer.com'];
export const MAX_ITEMS = 200;
export const CACHE_MS = 10 * 60 * 1000;

const ID = /^[0-9a-f]{24}$/;
const TIME = /^\d{2}:\d{2}$/;
const IMAGE = /^https:\/\/imagenes\.atresplayer\.com\//;

export const listUrl = (slug) => `https://www.atresplayer.com/${slug}/u7d/`;

/** May the explorer window go to this address? Only Atresplayer's own pages, over https. */
export function allowedAddress(url) {
  try {
    const u = new URL(url);
    return u.protocol === 'https:' && HOSTS.includes(u.hostname) && !u.port && !u.username;
  } catch {
    return false;
  }
}

const WATCH = /^https:\/\/www\.atresplayer\.com\/grabaciones\/([a-z0-9-]{2,40})\/([0-9a-f]{24})\/?$/i;

/** The page of a recording on atresplayer.com, normalised, or `null` if `url` is not one (the app opens nothing else to watch). */
export function watchAddress(url) {
  const m = WATCH.exec(String(url || ''));
  return m ? `https://www.atresplayer.com/grabaciones/${m[1].toLowerCase()}/${m[2].toLowerCase()}/` : null;
}

/** The recordings of a message of the plugin that are well formed, at most `MAX_ITEMS`, without repeats. */
export function cleanItems(items) {
  const seen = new Set();
  const out = [];
  for (const it of Array.isArray(items) ? items : []) {
    if (!it || typeof it !== 'object' || typeof it.id !== 'string' || !ID.test(it.id) || seen.has(it.id)) continue;
    const title = typeof it.title === 'string' ? it.title.trim().slice(0, 160) : '';
    if (!title) continue;
    seen.add(it.id);
    out.push({
      id: it.id,
      title,
      day: Number.isInteger(it.day) && it.day >= 1 && it.day <= 31 ? it.day : 0,
      time: typeof it.time === 'string' && TIME.test(it.time) ? it.time : '',
      image: typeof it.image === 'string' && it.image.length < 400 && IMAGE.test(it.image) ? it.image : '',
    });
    if (out.length >= MAX_ITEMS) break;
  }
  return out;
}

/**
 * One read of a channel's page: the plugin reports the programmes as the page shows them (`items`, more each time the
 * page loads another row) and says when it is `done`. `finish` is called once with `{items}` or `{error}`.
 */
export class Reading {
  constructor(slug, finish) {
    this.slug = slug;
    this.items = [];
    this.finish = (result) => {
      if (this.over) return;
      this.over = true;
      finish(result);
    };
    this.over = false;
  }

  /** A message of the plugin; the caller has already checked who sent it. */
  message(msg) {
    if (this.over || !msg || msg.slug !== this.slug) return;
    if (msg.type === 'items') this.items = cleanItems(msg.items);
    if (msg.type === 'done') this.end();
  }

  /** The window was closed or time ran out: what was read so far, or why there is nothing. */
  end(reason = 'sin datos') {
    this.finish(this.items.length ? { items: this.items } : { error: reason });
  }
}
