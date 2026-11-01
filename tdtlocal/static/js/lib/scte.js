// Ad-break markers (SCTE-35): the wording of the "Marcas" dialog and of the on-screen alerts, as pure functions.
import { ago } from './format.js';

export const KIND_LABELS = {
  'cue-out': 'Empieza una pausa de anuncios',
  'cue-in': 'Termina la pausa de anuncios',
  'cue-out-cont': 'Pausa de anuncios en curso',
  scte35: 'Mensaje SCTE-35',
  cue: 'Marca de corte (CUE)',
  interstitial: 'Anuncio intercalado (HLS)',
  asset: 'Anuncio (asset)',
  daterange: 'Metadatos con fecha (DATERANGE)',
  'ts-pid': 'La señal lleva un canal SCTE-35',
  emsg: 'La señal lleva eventos SCTE-35 (fMP4)',
};

/** Spanish name of a kind of marker; an unknown kind is shown as it comes. */
export const kindLabel = (kind) => KIND_LABELS[kind] || String(kind);

/** The text of an on-screen alert for one event: what happened, and its detail if there is one. */
export function alertText(ev) {
  return kindLabel(ev.kind) + (ev.detail ? ' · ' + ev.detail : '');
}

/**
 * The events that arrived after `afterId`, oldest first. `null` means "first look": the page only learns where
 * the log stands, so that opening it does not announce everything that was already there.
 * @param {Array<{id: number}>} events
 * @param {number | null} afterId
 */
export function arrivals(events, afterId) {
  if (afterId === null) return [];
  return events.filter((e) => e.id > afterId);
}

/**
 * One sentence about what the watcher is doing, from `status` in `/api/scte`.
 * @param {{enabled: boolean, scope: string, interval: number, events: number, scan: {running: boolean, done: number, total: number, errors: number, last: number | null}}} status
 */
export function statusLine(status, nowSec = Date.now() / 1000) {
  if (!status.enabled) return 'La vigilancia está desactivada. Actívala en Ajustes ▸ Marcas de anuncios.';
  if (status.scope === 'viewing') return 'Vigilando lo que estás viendo. Para explorar más canales, cámbialo en Ajustes.';
  const what = status.scope === 'all' ? 'todos los canales con directo' : 'los canales de tu lista';
  const scan = status.scan;
  const state = scan.running
    ? ` Explorando ahora: ${scan.done} de ${scan.total}.`
    : scan.last ? ` Última exploración ${ago(scan.last, nowSec)}${scan.errors ? `, con ${scan.errors} que no respondieron` : ''}.` : '';
  return `Explorando ${what} cada ${status.interval} s.${state}`;
}

/** "3 marcas en 2 canales" for the summary rows of `/api/scte?summary=1`. */
export function summaryText(rows) {
  const total = rows.reduce((n, r) => n + r.count, 0);
  if (!total) return 'Todavía no se ha encontrado ninguna marca.';
  return `${total} ${total === 1 ? 'marca' : 'marcas'} en ${rows.length} ${rows.length === 1 ? 'canal' : 'canales'}.`;
}
