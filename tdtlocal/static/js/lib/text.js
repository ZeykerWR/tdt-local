// Text helpers shared by search, voice alerts and the assistant.

/** Lower-case and accent-free form used to compare what the user types with channel names. */
export const norm = (s) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

/** Words only, separated by single spaces: "La 2 (HD)" -> "la 2 hd". */
export const slug = (s) => norm(s).replace(/[^a-z0-9]+/g, ' ').trim();

/** Two-letter placeholder for a channel without logo. */
export const initials = (name) => name.replace(/[^\p{L}\p{N}]/gu, '').slice(0, 2).toUpperCase();
