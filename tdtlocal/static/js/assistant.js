// The assistant overlay (Ctrl+K): commands resolved in the browser, everything else goes to the local model.
import { postJson } from './api.js';
import { $, el } from './dom.js';
import { quickCommand } from './lib/commands.js';
import { toggleGuide, isGuideOpen } from './guide.js';
import { cur, state } from './state.js';

const assistEl = $('assist');
const askIn = $('askInput');
const askOut = $('askOut');
const REQUEST_TIMEOUT_MS = 170000;

export const isAssistantOpen = () => !assistEl.hidden;

export function toggleAssist(open) {
  const show = open === undefined ? assistEl.hidden : open;
  assistEl.hidden = !show;
  $('btnAsk').setAttribute('aria-pressed', show ? 'true' : 'false');
  if (show) { askIn.focus(); askIn.select(); }
}

/**
 * @param {{setKind: (k: string) => void, play: (c: object) => void,
 *          multiWith: (chs: object[], rotate: number|null) => void, toMosaic: (c: object) => void}} actions
 */
export function initAssistant(actions) {
  const showIn = (c) => { if (c.kind !== state.kind) actions.setKind(c.kind); };

  function runActions(list) {
    const done = [];
    for (const a of list) {
      if (a.do === 'kind') {
        actions.setKind(a.kind);
        done.push(a.kind === 'radio' ? 'radio' : 'televisión');
      } else if (a.do === 'play') {
        const c = state.byId.get(a.id);
        if (c) { showIn(c); actions.play(c); done.push(c.name); }
      } else if (a.do === 'multi') {
        const chs = a.ids.map((id) => state.byId.get(id)).filter(Boolean);
        actions.multiWith(chs, a.rotate);
        done.push('multivisión: ' + chs.map((c) => c.name).join(', ') + (a.rotate ? ' (rotando cada ' + state.rot.secs + ' s)' : ''));
      } else if (a.do === 'guide') {
        if (!isGuideOpen()) toggleGuide();
        done.push('guía');
      }
    }
    return done;
  }

  function showAnswer(say, done, results) {
    const nodes = [];
    if (say) nodes.push(el('p', 'assist-say', say));
    if (done.length) nodes.push(el('p', 'assist-done', 'Hecho: ' + done.join(' · ')));
    for (const r of results) {
      const c = state.byId.get(r.id);
      if (!c) continue;
      const row = el('div', 'assist-res');
      const txt = el('span', 'assist-res-txt');
      txt.append(el('strong', '', c.name), el('span', '', r.why));
      const ver = el('button', 'btn', 'Ver');
      ver.type = 'button';
      ver.addEventListener('click', () => { showIn(c); actions.play(c); });
      const add = el('button', 'btn', 'Al mosaico');
      add.type = 'button';
      add.addEventListener('click', () => { showIn(c); actions.toMosaic(c); });
      row.append(txt, ver, add);
      nodes.push(row);
    }
    askOut.replaceChildren(...nodes);
  }

  let asking = false;
  $('askForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const q = askIn.value.trim();
    if (!q || asking) return;
    const quick = quickCommand(q, state.channels, state.kind);
    if (quick) { showAnswer('', runActions(quick), []); return; }
    asking = true;
    $('askGo').disabled = true;
    askOut.replaceChildren(el('p', 'assist-wait', 'Pensando… el modelo local puede tardar unos segundos.'));
    const ctrl = new AbortController();
    const timeout = setTimeout(() => ctrl.abort(), REQUEST_TIMEOUT_MS);
    try {
      const r = await postJson('/api/ai', { q, kind: state.kind, current: cur() ? cur().id : '' }, { signal: ctrl.signal });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) showAnswer(d.error || 'El asistente no ha podido responder.', [], []);
      else showAnswer(d.say, runActions(d.actions || []), d.results || []);
    } catch {
      showAnswer('El asistente no ha respondido a tiempo.', [], []);
    } finally {
      clearTimeout(timeout);
      asking = false;
      $('askGo').disabled = false;
    }
  });
  $('askClose').addEventListener('click', () => toggleAssist(false));
  $('btnAsk').addEventListener('click', () => toggleAssist());
}
