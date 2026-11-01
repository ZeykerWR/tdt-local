// The "Registro" tab of the settings (desktop app only): the app's log, to read it and to send it when something fails.
// The lines come as `2026-11-01 19:45:07 WARN  [explorar] texto` (desktop/lib/logbook.js).

export const MODES = { all: 'Todo', problems: 'Solo avisos y errores' };
export const SHOWN = 400; // lines shown at once: the file has the rest

const LEVEL = /^\S+ \S+ (INFO|WARN|ERROR)\s/;

/** `INFO`, `WARN` or `ERROR` of a line (`INFO` for one that does not say). */
export const levelOf = (line) => (LEVEL.exec(line) || [])[1] || 'INFO';

/** The lines that pass the filter, keeping the order; at most the last `limit`. */
export function filterLines(lines, mode, limit = SHOWN) {
  const kept = mode === 'problems' ? lines.filter((l) => levelOf(l) !== 'INFO') : lines;
  return kept.slice(-limit);
}

/** "312 líneas (4 avisos, 1 error)". */
export function summarize(lines) {
  const count = (level) => lines.filter((l) => levelOf(l) === level).length;
  const warns = count('WARN');
  const errors = count('ERROR');
  const noun = (n, one, many) => n + ' ' + (n === 1 ? one : many);
  const problems = [warns && noun(warns, 'aviso', 'avisos'), errors && noun(errors, 'error', 'errores')].filter(Boolean);
  return noun(lines.length, 'línea', 'líneas') + (problems.length ? ' (' + problems.join(', ') + ')' : '');
}

export const LOGS_INTRO = 'Lo que va pasando en la aplicación: el arranque, los plugins, la ventana de exploración, el servidor y '
  + 'los errores de la página y de los reproductores de dentro. Se guarda también en un archivo. Si algo falla, copia o guarda el '
  + 'registro y envíalo. Léelo antes: puede incluir direcciones de canales y de páginas que hayas abierto (se ocultan las '
  + 'claves y los tokens que salgan en una dirección).';
