// Runs in every frame of the window (also the ones of other sites inside it). It asks the main process which plugin
// scripts belong to this frame and runs them in an isolated world of their own, which is where the scripts of an
// extension run too (they see the page's DOM, the page does not see their variables). Only the page of TDT local gets
// something in return: `window.tdtDesktop`, at the end of this file.
const { contextBridge, ipcRenderer, webFrame } = require('electron');

const FIRST_WORLD = 1001; // 0 is the page's and 999 is Electron's

function run() {
  if (!/^https?:$/.test(location.protocol)) return;
  let plugins;
  try {
    plugins = ipcRenderer.sendSync('tdt:plugin-scripts');
  } catch {
    return;
  }
  (plugins || []).forEach((plugin, index) => {
    webFrame.executeJavaScriptInIsolatedWorld(
      FIRST_WORLD + index,
      plugin.scripts.map((s) => ({ code: s.code, url: `tdt-plugin://${plugin.id}/${s.file}` })),
    ).catch((error) => console.warn('[TDT plugins]', plugin.id, error && error.message));
  });
}

if (document.readyState === 'loading') window.addEventListener('DOMContentLoaded', run, { once: true });
else run();

// The plugin that reads Atresplayer's list tells what it read with postMessage in its own page. The page cannot be
// trusted (it can send the same message), so this only passes it on: the main process checks who it comes from and
// cleans every field.
if (window.top === window) {
  window.addEventListener('message', (event) => {
    const d = event.data;
    if (event.source !== window || !d || typeof d !== 'object' || d.source !== 'tdt-u7d') return;
    if (d.type === 'items' || d.type === 'done') {
      ipcRenderer.send('tdt:u7d-read', { type: d.type, slug: String(d.slug || ''), items: d.type === 'items' ? d.items : undefined });
    }
  });
}

// The page of TDT local itself (never a frame inside it) can manage the plugins from its settings. The main process
// checks again who asks on every call, so this being here gives nothing to any other page.
if (window.top === window && location.hostname === '127.0.0.1') {
  contextBridge.exposeInMainWorld('tdtDesktop', {
    plugins: {
      list: () => ipcRenderer.invoke('tdt:plugins-list'),
      setEnabled: (id, on) => ipcRenderer.invoke('tdt:plugins-set', String(id), !!on),
      rescan: () => ipcRenderer.invoke('tdt:plugins-rescan'),
      openFolder: () => ipcRenderer.invoke('tdt:plugins-folder'),
    },
    atres: {
      list: (slug) => ipcRenderer.invoke('tdt:atres-list', String(slug)),
      watch: (address, title) => ipcRenderer.invoke('tdt:atres-watch', String(address), String(title || '')),
    },
    logs: {
      get: () => ipcRenderer.invoke('tdt:logs-get'),
      save: () => ipcRenderer.invoke('tdt:logs-save'),
      openFolder: () => ipcRenderer.invoke('tdt:logs-folder'),
    },
    reload: () => ipcRenderer.invoke('tdt:reload'),
  });
}
