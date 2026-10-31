// Modal dialogs: own channels (pasted link + optional headers) and voice-alert words.
import { postJson } from './api.js';
import { $ } from './dom.js';
import { parseAlertWords } from './lib/alerts.js';
import { cur, state } from './state.js';
import { store } from './store.js';

// Headers some providers check before serving a stream. They are sent by the proxy, nothing more.
const ATRES_HEADERS = { Origin: 'https://www.atresplayer.com', Referer: 'https://www.atresplayer.com/directos/lasexta/' };

/**
 * @param {{setKind: (k: string) => void, play: (c: object) => void, load: (force: boolean) => Promise<void>,
 *          footMsg: (t: string) => void, updateDeck: () => void, syncStt: () => void,
 *          syncAlertUi: () => void, saveMulti: () => void, clearActive: () => void}} app
 */
export function initDialogs(app) {
  initOwnChannels(app);
  initAlerts(app);
}

function initOwnChannels(app) {
  const dlg = $('addDlg');
  const message = (t) => { $('addMsg').textContent = t; };
  $('btnAdd').addEventListener('click', () => { message(''); dlg.showModal(); $('addName').focus(); });
  $('addCancel').addEventListener('click', () => dlg.close());
  $('addHdr').addEventListener('change', () => { $('addExtra').hidden = $('addHdr').value !== 'custom'; });

  $('addForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const choice = $('addHdr').value;
    const headers = choice === 'atres' ? ATRES_HEADERS
      : choice === 'custom' ? { Origin: $('addOrigin').value.trim(), Referer: $('addReferer').value.trim() } : {};
    const kind = $('addKind').value;
    let res;
    try {
      const r = await postJson('/api/custom', { name: $('addName').value, kind, sources: [$('addUrl').value.trim()], headers });
      res = await r.json();
    } catch { message('El servidor local no responde.'); return; }
    if (!res.ok) { message(res.error || 'No se pudo añadir el canal.'); return; }
    dlg.close();
    $('addForm').reset();
    $('addExtra').hidden = true;
    if (state.kind !== kind) app.setKind(kind);
    state.cat = '';
    state.grp = '';
    await app.load(true);
    const c = state.byId.get(res.id);
    if (c) app.play(c);
  });

  $('btnDel').addEventListener('click', async () => {
    const c = cur();
    if (!c || !c.custom || !window.confirm('¿Quitar «' + c.name + '» de tus canales propios?')) return;
    try {
      await postJson('/api/custom/delete', { id: c.id });
    } catch { app.footMsg('El servidor local no responde.'); return; }
    app.clearActive();
    app.saveMulti();
    await app.load(true);
  });
}

function initAlerts(app) {
  const dlg = $('alertDlg');
  $('btnAlert').addEventListener('click', () => {
    $('alertWords').value = state.alerts.words.join(', ');
    $('alertOn').checked = state.alerts.on;
    $('alertJump').checked = state.alerts.jump;
    dlg.showModal();
  });
  $('alertCancel').addEventListener('click', () => dlg.close());
  $('alertForm').addEventListener('submit', (e) => {
    e.preventDefault();
    const words = parseAlertWords($('alertWords').value);
    state.alerts = { words, on: $('alertOn').checked && words.length > 0, jump: $('alertJump').checked };
    store.set('alerts', state.alerts);
    dlg.close();
    app.syncAlertUi();
    app.syncStt();
    app.updateDeck();
  });
}
