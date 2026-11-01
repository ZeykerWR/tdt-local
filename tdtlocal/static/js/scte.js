// The "Marcas" dialog (ad-break markers, SCTE-35) and the polling that raises an on-screen alert when a new one appears.
import { api, requestJson } from './api.js';
import { $, el } from './dom.js';
import { alertText, arrivals, kindLabel, statusLine, summaryText } from './lib/scte.js';

const POLL_MS = 10000;
const FAST_MS = 2000; // while the page reacts to ad breaks, a marker must be seen before it is played
const SHOWN = 200;
let hooks = null;
let timer = null;
let period = POLL_MS;
let lastId = null; // null until the first answer: opening the page must not announce what was already logged
let unseen = 0;

const dlg = () => $('scteDlg');

function paintButton() {
  $('btnScte').textContent = unseen ? `Marcas (${unseen})` : 'Marcas';
  $('btnScte').classList.toggle('alerting', unseen > 0);
}

async function poll() {
  let res;
  try { res = await api('/api/scte?limit=' + (lastId === null ? 0 : 50) + '&after=' + (lastId || 0)); } catch { return; }
  if (!res.ok || !res.data) return;
  const d = res.data;
  if (lastId !== null && d.last_id < lastId) lastId = null; // the log was emptied or replaced: start over quietly
  const fresh = arrivals(d.events, lastId);
  lastId = d.last_id;
  if (dlg().open) refresh();
  if (!fresh.length) return;
  if (hooks.react) hooks.react(fresh);
  unseen += fresh.length;
  paintButton();
  if (d.notify) {
    const last = fresh[fresh.length - 1];
    hooks.notify(last.name, alertText(last), fresh.length);
  }
}

function row(ev) {
  const li = el('li', 'scte-row ' + ev.kind);
  li.title = ev.raw || '';
  const head = el('div', 'scte-head');
  head.append(el('time', '', new Date(ev.ts * 1000).toLocaleString('es-ES')), el('strong', '', ev.name || ev.channel));
  const what = el('div', 'scte-what', kindLabel(ev.kind) + (ev.detail ? ' · ' + ev.detail : ''));
  const where = el('div', 'dlg-hint', 'Detectado en ' + (ev.source || '') + (ev.url ? ' · ' + ev.url : ''));
  li.append(head, what, where);
  return li;
}

async function refresh() {
  let res;
  try { res = await api('/api/scte?summary=1&limit=' + SHOWN); } catch { $('scteStatus').textContent = 'El servidor local no responde.'; return; }
  if (!res.ok || !res.data) return;
  const d = res.data;
  $('scteStatus').textContent = statusLine(d.status) + ' ' + summaryText(d.summary || []);
  $('scteScan').disabled = !d.status.enabled || d.status.scope === 'viewing' || d.status.scan.running;
  const items = d.events.slice().reverse().map(row);
  $('scteList').replaceChildren(...(items.length ? items : [el('li', 'dlg-hint', 'El registro está vacío.')]));
  const channels = (d.summary || []).slice(0, 12).map((r) => `${r.name || r.channel} (${r.count})`);
  $('scteChannels').textContent = channels.length ? 'Canales con marcas: ' + channels.join(' · ') : '';
}

async function scanNow() {
  const res = await requestJson('/api/scte/scan', 'POST', {}).catch(() => null);
  $('scteMsg').textContent = res && res.data && res.data.ok ? 'Exploración pedida: tarda unos segundos.' : (res && res.data && res.data.error) || 'No se pudo pedir la exploración.';
  setTimeout(refresh, 2500);
}

async function clearLog() {
  if (!window.confirm('¿Vaciar el registro de marcas? No se puede deshacer.')) return;
  const res = await requestJson('/api/scte/clear', 'POST', {}).catch(() => null);
  $('scteMsg').textContent = res && res.ok ? 'Registro vaciado.' : 'No se pudo vaciar (solo se puede desde el propio equipo).';
  refresh();
}

export async function openScte() {
  unseen = 0;
  paintButton();
  $('scteMsg').textContent = '';
  await refresh();
  if (!dlg().open) dlg().showModal();
}

/**
 * Show or hide the button and start or stop watching for new markers, according to the server's settings.
 * @param {boolean} enabled
 * @param {boolean} [fast] - something reacts to the markers: look more often
 */
export function syncScte(enabled, fast = false) {
  $('btnScte').hidden = !enabled;
  const wanted = fast ? FAST_MS : POLL_MS;
  if (enabled && (!timer || wanted !== period)) {
    clearInterval(timer);
    period = wanted;
    timer = setInterval(poll, period);
    poll();
  } else if (!enabled && timer) {
    clearInterval(timer);
    timer = null;
    lastId = null;
    unseen = 0;
    paintButton();
  }
}

/**
 * @param {{notify: (channel: string, text: string, count: number) => void, react?: (events: object[]) => void}} appHooks
 */
export function initScte(appHooks) {
  hooks = appHooks;
  $('btnScte').addEventListener('click', openScte);
  $('scteClose').addEventListener('click', () => dlg().close());
  $('scteScan').addEventListener('click', scanNow);
  $('scteClear').addEventListener('click', clearLog);
}
