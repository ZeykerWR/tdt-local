// Atresmedia's channels, added with one click through Atresplayer's own embeddable player (shown in an <iframe>, like
// YouTube: its player, its ads and its cookie notice; nothing goes through the proxy). Mediaset is not here: Mediaset
// Infinity forbids being embedded in other pages (`frame-ancestors`) and that is respected; its channels are already
// in the lists, as links to its web.

const EMBED = /^https:\/\/www\.atresplayer\.com\/embed\/live\/([a-z0-9-]{2,40})\/?(?:[?#].*)?$/i;

/** Address of the embeddable live player of an Atresmedia channel (`lasexta`, `antena3`…). */
export const atresLink = (slug) => 'https://www.atresplayer.com/embed/live/' + slug + '/';

/** The embed URL for an Atresplayer live-player link, or `null` if `url` is not one. */
export function atresEmbed(url) {
  const m = EMBED.exec(String(url || ''));
  return m ? atresLink(m[1].toLowerCase()) : null;
}

/** The channel's own page on atresplayer.com, for the "Abrir la web de la cadena" button, or `''`. */
export function atresWeb(url) {
  const m = EMBED.exec(String(url || ''));
  return m ? 'https://www.atresplayer.com/directos/' + m[1].toLowerCase() + '/' : '';
}

// `epg` is the channel's id in the community guide (see EPG_EXTRA_SOURCE in config.py), `icon` its picon there
const PICONS = 'https://raw.githubusercontent.com/davidmuma/picons_dobleM/master/icon/';
const atres = (name, slug, epg, icon) => ({
  name,
  sources: [atresLink(slug)],
  web: 'https://www.atresplayer.com/directos/' + slug + '/',
  epg,
  logo: PICONS + encodeURIComponent(icon) + '.png',
});

export const GROUPS = {
  atresmedia: {
    name: 'Atresmedia',
    channels: [
      atres('Antena 3', 'antena3', 'Antena 3 HD', 'Antena 3'), atres('La Sexta', 'lasexta', 'La Sexta HD', 'La Sexta'),
      atres('Neox', 'neox', 'Neox', 'Neox'), atres('Nova', 'nova', 'Nova', 'Nova'), atres('Mega', 'mega', 'Mega', 'Mega'),
      atres('Atreseries', 'atreseries', 'Atreseries', 'Atreseries'),
    ],
  },
};

/**
 * The channels of a group that still need something: their embedded player is not yet among the sources of one of
 * `existing` (own channels), or the channel that has it has no guide yet. A channel of the same name that has a
 * stream but not the player is not skipped: the player is added to it.
 * @param {string} groupId
 * @param {Array<{custom?: boolean, epg?: string, sources?: Array<{u: string}>}>} existing
 * @returns {Array<{name: string, sources: string[], web: string, epg: string, logo: string}>}
 */
export function missingOf(groupId, existing) {
  const own = existing.filter((c) => c.custom);
  return GROUPS[groupId].channels.filter((entry) => !own.some((c) => c.epg
    && entry.sources.every((u) => (c.sources || []).some((s) => s.u === u))));
}
