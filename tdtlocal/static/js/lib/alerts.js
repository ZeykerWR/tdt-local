// Voice alerts: words the user wants to be told about when they are said on any tile.
import { norm } from './text.js';

export const MAX_ALERT_WORDS = 20;
export const MIN_WORD_LENGTH = 3;
export const ALERT_COOLDOWN_MS = 20000;

/** "Terremoto, Real Madrid" -> ["terremoto", "real madrid"]: normalised, unique, at least 3 letters. */
export function parseAlertWords(text) {
  const words = text.split(/[,\n]/).map((w) => norm(w).trim()).filter((w) => w.length >= MIN_WORD_LENGTH);
  return [...new Set(words)].slice(0, MAX_ALERT_WORDS);
}

/** The watched words (already normalised) that appear in `text`, ignoring case and accents. */
export function matchingWords(text, words) {
  const nt = norm(text);
  return words.filter((w) => nt.includes(w));
}
