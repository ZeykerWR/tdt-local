// The log of the desktop app: what happened (start, plugins, the explorer window, the Python server, errors of the page and
// of the players inside it), kept in memory and in a file, so the user can look at it and send it when something fails.
// Nothing here needs Electron.
import { appendFileSync, mkdirSync, renameSync, statSync } from 'node:fs';
import { dirname } from 'node:path';

export const LEVELS = ['INFO', 'WARN', 'ERROR'];
const MAX_LINE = 600;
// keys and tokens that travel in an address or a header must not end up in a file the user is going to send
const SECRET = /\b(token|auth|authorization|password|passwd|secret|api[_-]?key|apikey|sid|jwt|bearer)(=|%3D|:\s*)([^&\s"']{3,})/gi;
// a header that carries a credential is hidden whole (`Authorization: Bearer xyz`, cookies); a bare `Bearer xyz` too
const HEADER = /\b(authorization|proxy-authorization|cookie|set-cookie|x-api-key)(:\s*)[^\n]*/gi;
const BEARER = /\b(Bearer|Basic)\s+[\w.~+/=-]{6,}/g;

export const scrub = (text) => String(text)
  .replace(HEADER, '$1$2[oculto]')
  .replace(BEARER, '$1 [oculto]')
  .replace(SECRET, '$1$2[oculto]');

/** `INFO`, `WARN` or `ERROR` for a line that comes without a level (the output of the Python server). */
export function levelOf(text) {
  if (/Traceback|\bError\b|Exception|CRITICAL|\bFATAL\b/i.test(text)) return 'ERROR';
  if (/\bAVISO\b|\bWARN(ING)?\b/i.test(text)) return 'WARN';
  return 'INFO';
}

export class Logbook {
  /**
   * @param {{max?: number, file?: string, maxBytes?: number, now?: () => Date}} options
   *   `max` lines kept in memory; `file` where they are also written (`file.1` keeps the previous one once it passes `maxBytes`)
   */
  constructor({ max = 2000, file = '', maxBytes = 1_000_000, now = () => new Date() } = {}) {
    this.max = max;
    this.file = file;
    this.maxBytes = maxBytes;
    this.now = now;
    this.kept = [];
    this.fileOk = !!file;
  }

  /** Adds one line per line of `text`. Returns the lines it wrote. */
  add(source, level, text) {
    const lvl = LEVELS.includes(level) ? level : 'INFO';
    const stamp = this.now().toISOString().slice(0, 19).replace('T', ' ');
    const out = [];
    for (const raw of String(text).split(/\r?\n/)) {
      const line = scrub(raw).trimEnd();
      if (!line) continue;
      out.push(`${stamp} ${lvl.padEnd(5)} [${source}] ${line.length > MAX_LINE ? line.slice(0, MAX_LINE) + '…' : line}`);
    }
    for (const line of out) this.kept.push(line);
    if (this.kept.length > this.max) this.kept.splice(0, this.kept.length - this.max);
    this.write(out);
    return out;
  }

  write(lines) {
    if (!this.fileOk || !lines.length) return;
    try {
      mkdirSync(dirname(this.file), { recursive: true });
      try {
        if (statSync(this.file).size > this.maxBytes) renameSync(this.file, this.file + '.1');
      } catch { /* there is no file yet */ }
      appendFileSync(this.file, lines.join('\n') + '\n', 'utf8');
    } catch {
      this.fileOk = false; // a full or protected disk must not stop the app: the log stays in memory
    }
  }

  /** The last `limit` lines. */
  lines(limit = this.max) {
    return this.kept.slice(-limit);
  }

  text(limit = this.max) {
    return this.lines(limit).join('\n');
  }
}
