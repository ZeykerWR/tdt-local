// DOM helpers.
import { initials } from './lib/text.js';

export const $ = (id) => document.getElementById(id);

/** Create an element with an optional class and text. */
export function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
}

/** Initials as a placeholder; the logo is laid over them when it loads (and dropped if it fails). */
export function fillLogo(box, channel) {
  box.replaceChildren(el('span', '', initials(channel.name)));
  if (!channel.logo) return;
  const img = new Image();
  img.alt = '';
  img.loading = 'lazy';
  img.decoding = 'async';
  img.addEventListener('load', () => img.classList.add('ld'));
  img.addEventListener('error', () => img.remove());
  img.src = '/logo?u=' + encodeURIComponent(channel.logo);
  box.append(img);
}
