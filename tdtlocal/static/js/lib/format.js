// Human-readable dates and times (Spanish).

const rtf = new Intl.RelativeTimeFormat('es', { numeric: 'auto' });

/** "hace 3 horas" for a timestamp in seconds; `nowSec` is injectable for tests. */
export function ago(ts, nowSec = Date.now() / 1000) {
  if (!ts) return 'nunca';
  const s = Math.round(nowSec - ts);
  if (s < 90) return 'ahora mismo';
  const m = Math.round(s / 60);
  if (m < 90) return rtf.format(-m, 'minute');
  const h = Math.round(m / 60);
  if (h < 48) return rtf.format(-h, 'hour');
  return rtf.format(-Math.round(h / 24), 'day');
}

/** "20:30" for a timestamp in seconds. */
export const hhmm = (ts) => new Date(ts * 1000).toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' });

/** "Hoy", "Mañana" or "viernes, 5 de marzo" for a timestamp in seconds. */
export function dayLabel(ts, now = new Date()) {
  const d = new Date(ts * 1000);
  const midnight = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const diff = Math.round((midnight(d) - midnight(now)) / 86400000);
  if (diff === 0) return 'Hoy';
  if (diff === 1) return 'Mañana';
  return d.toLocaleDateString('es-ES', { weekday: 'long', day: 'numeric', month: 'long' });
}
