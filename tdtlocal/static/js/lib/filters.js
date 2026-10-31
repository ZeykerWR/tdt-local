// Which channels the list shows.
import { norm } from './text.js';

/**
 * Channels of the current list that pass the filters.
 * @param {Array} channels
 * @param {{kind: string, onlyStream: boolean, hideDown: boolean, cat: string, grp: string,
 *          onlyFav: boolean, favs: Set<string>, query: string}} f
 */
export function filterChannels(channels, f) {
  const query = norm(f.query.trim());
  return channels.filter((c) => {
    if (!isListed(c, f)) return false;
    if (f.cat && c.category !== f.cat) return false;
    if (f.grp && c.group !== f.grp) return false;
    if (f.onlyFav && !f.favs.has(c.id)) return false;
    return !query || norm(c.name + ' ' + c.group + ' ' + c.category).includes(query);
  });
}

/** Passes the filters that do not depend on category, group, favourites or search. */
export const isListed = (c, f) => c.kind === f.kind && (!f.onlyStream || c.sources.length > 0) && !(f.hideDown && c.ok === false);

/** Categories (in list order) and, for the chosen one, its groups. */
export function categoriesOf(channels, kind, cat) {
  const ofKind = channels.filter((c) => c.kind === kind);
  return {
    cats: [...new Set(ofKind.map((c) => c.category))],
    groups: cat ? [...new Set(ofKind.filter((c) => c.category === cat && c.group).map((c) => c.group))] : [],
  };
}
