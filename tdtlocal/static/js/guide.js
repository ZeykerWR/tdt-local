// Programme guide of the active channel (overlay opened with G).
import { api } from './api.js';
import { $, el } from './dom.js';
import { dayLabel, hhmm } from './lib/format.js';
import { cur, nowTs } from './state.js';

const guideEl = $('guide');
let guideFor = null; // epg id whose guide is on screen
let guideSeq = 0; // discards answers that arrive after the user moved on

export const isGuideOpen = () => !guideEl.hidden;

const epgIdOf = (c) => (c && c.epg ? c.epg : '');

async function loadGuide() {
  const c = cur();
  $('guideTitle').textContent = c ? 'Programación · ' + c.name : 'Programación';
  guideFor = epgIdOf(c);
  const body = $('guideBody');
  const say = (t) => body.replaceChildren(el('p', 'guide-empty', t));
  if (!c) { say('Elige un canal.'); return; }
  if (!guideFor) { say('Este canal no tiene guía de programación.'); return; }
  const seq = ++guideSeq;
  say('Cargando…');
  let r = null;
  try { r = await api('/api/epg?id=' + encodeURIComponent(guideFor)); } catch { /* no server */ }
  if (seq !== guideSeq) return;
  const items = r && r.ok && r.data && r.data.programmes ? r.data.programmes : [];
  if (!items.length) { say('Sin programación disponible ahora mismo.'); return; }
  const t = nowTs();
  let day = '';
  const nodes = [];
  for (const [s, e, title, desc, cat] of items) {
    const dl = dayLabel(s);
    if (dl !== day) { day = dl; nodes.push(el('h4', 'guide-day', dl)); }
    const live = s <= t;
    const d = el('details', 'guide-item' + (live ? ' live' : ''));
    d.open = live;
    const sum = el('summary');
    sum.append(el('span', 'g-time', hhmm(s)), el('span', 'g-title', title));
    if (live) sum.append(el('span', 'g-live', 'Ahora'));
    const det = el('div', 'g-detail');
    det.append(el('p', '', desc || 'Sin descripción.'),
      el('p', 'g-meta', hhmm(s) + '–' + hhmm(e) + (cat ? ' · ' + cat : '')));
    d.append(sum, det);
    nodes.push(d);
  }
  body.replaceChildren(...nodes);
  body.scrollTop = 0;
}

/** With the guide open, follow the active channel (also when the multi-view rotates). */
export function syncGuide() {
  if (guideEl.hidden) return;
  const c = cur();
  $('guideTitle').textContent = c ? 'Programación · ' + c.name : 'Programación';
  if (epgIdOf(c) !== guideFor) loadGuide();
}

export function toggleGuide() {
  guideEl.hidden = !guideEl.hidden;
  $('btnGuide').setAttribute('aria-pressed', guideEl.hidden ? 'false' : 'true');
  if (!guideEl.hidden) loadGuide();
}
