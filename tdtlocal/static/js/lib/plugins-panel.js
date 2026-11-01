// The "Plugins" tab of the settings, which only exists in the desktop app. What the app says about each plugin
// (desktop/main.js: pluginList) becomes the text the panel shows.

/** The sites a plugin acts on, as people say them: `www.atresplayer.com`, not `https://www.atresplayer.com/embed/live/*`. */
export function hostsOf(patterns) {
  const hosts = [];
  for (const pattern of patterns || []) {
    const m = /^(?:https?|\*):\/\/([^/]+)\//.exec(String(pattern));
    if (m && !hosts.includes(m[1])) hosts.push(m[1]);
  }
  return hosts;
}

/**
 * @param {{name: string, version: string, description: string, source: string, sites: string[], problems: string[], enabled: boolean}} plugin
 */
export function describePlugin(plugin) {
  const usable = !plugin.problems.length;
  const hosts = hostsOf(plugin.sites);
  return {
    title: plugin.name + (plugin.version ? ' ' + plugin.version : ''),
    description: plugin.description,
    usable,
    on: usable && plugin.enabled,
    acts: hosts.length ? 'Actúa solo en: ' + hosts.join(', ') + '.' : '',
    source: plugin.source ? 'Viene de: ' + plugin.source + '.' : '',
    problems: plugin.problems,
  };
}

export function summarize(plugins) {
  if (!plugins.length) return 'No hay ningún plugin.';
  const on = plugins.filter((p) => p.enabled && !p.problems.length).length;
  const word = plugins.length === 1 ? '1 plugin' : plugins.length + ' plugins';
  return word + (on ? ', ' + (on === 1 ? '1 activado' : on + ' activados') : ', ninguno activado') + '.';
}

export const PLUGINS_INTRO = 'Un plugin es una carpeta con un manifest.json que ejecuta sus propios scripts dentro de '
  + 'las páginas que declara (por ejemplo el reproductor incrustado de un canal). No hace peticiones, no pide permisos y '
  + 'sus scripts se leen de su carpeta, nunca de internet. Todos empiezan desactivados.';
