// Capturar el enlace del directo que estás viendo en tu navegador y llevarlo a TDT local.
//
// Cómo se usa:
//   1. En tu navegador abre la página del directo (por ejemplo la de laSexta en atresplayer.com), acepta o rechaza
//      las cookies como prefieras y deja que el vídeo empiece a reproducirse.
//   2. Pulsa F12, abre la pestaña «Consola», pega TODO este archivo y pulsa Intro. (Chrome y Edge piden que escribas
//      «allow pasting» la primera vez.)
//   3. Se abre una pestaña de TDT local con el diálogo «Añadir canal» ya relleno: revísalo y pulsa «Añadir».
//
// Qué hace: mira las listas .m3u8 que la página ya ha pedido (lo mismo que verías en la pestaña «Red» de las
// herramientas del navegador) y elige la más probable. No hace ninguna petición a la web, no se salta nada y solo
// funciona con lo que tu navegador ya está reproduciendo. Si el puerto de TDT local no es el 8788, cámbialo abajo.
// Ojo: estos enlaces llevan un permiso temporal y caducan; cuando deje de verse, repite el proceso. Y el permiso va
// atado a la IP desde la que se pidió: usa un navegador que salga a internet igual que TDT local (sin VPN, si TDT local
// no la usa); si no, el origen rechazará los trozos de vídeo (HTTP 492).
(function () {
  'use strict';
  const PUERTO = 8788;
  const ESPERA_MS = 8000; // if the page has not asked for a playlist yet, wait this long for one
  // names of the playlists of one quality or one audio track: the master playlist, if there is one, is better
  const VARIANTE = /(chunk|media|rendition|variant|audio|video|index_\d|\/\d{3,4}p?\/|_\d{3,4}p?\.)/i;

  const sinConsulta = (url) => String(url).split(/[?#]/)[0];

  /** The .m3u8 URLs among resource-timing entries, in order of first request. The newest URL of each is kept
   *  (it carries the most recent token). */
  function listas(entradas) {
    const vistas = new Map();
    for (const e of entradas) {
      if (!/\.m3u8(\?|#|$)/i.test(e.name)) continue;
      const clave = sinConsulta(e.name);
      const antes = vistas.get(clave);
      vistas.set(clave, { url: e.name, t: antes ? antes.t : e.startTime });
    }
    return [...vistas.values()].sort((a, b) => a.t - b.t);
  }

  /** The one to offer: the first playlist that does not look like one quality or track, else the first. */
  function principal(encontradas) {
    return encontradas.find((l) => !VARIANTE.test(sinConsulta(l.url))) || encontradas[0];
  }

  /** "La Sexta en directo | atresplayer" -> "La Sexta" */
  function nombreDe(titulo) {
    const limpio = String(titulo || '').split(/\s[|·–—-]\s/)[0].replace(/\s+en\s+directo.*$/i, '').trim();
    return limpio.slice(0, 80) || 'Canal propio';
  }

  /** The address that opens TDT local with the "Añadir canal" dialog filled in (the fragment never leaves the PC). */
  function enlaceTdt(puerto, url, nombre, host) {
    const cabeceras = /(^|\.)atresplayer\.com$/i.test(host || '') ? 'atres' : '';
    const partes = [['add', url], ['name', nombre], ['kind', 'tv']];
    if (cabeceras) partes.push(['hdr', cabeceras]);
    return 'http://127.0.0.1:' + puerto + '/#' + partes.map(([k, v]) => k + '=' + encodeURIComponent(v)).join('&');
  }

  function esperar(ms) {
    return new Promise((resolve) => {
      if (typeof PerformanceObserver === 'undefined') { resolve([]); return; }
      const vistas = [];
      const observador = new PerformanceObserver((lista) => vistas.push(...lista.getEntries()));
      try { observador.observe({ type: 'resource', buffered: true }); } catch (e) { resolve([]); return; }
      setTimeout(() => { observador.disconnect(); resolve(listas(vistas)); }, ms);
    });
  }

  async function main() {
    if (performance.setResourceTimingBufferSize) performance.setResourceTimingBufferSize(2000);
    let encontradas = listas(performance.getEntriesByType('resource'));
    const video = document.querySelector('video');
    if (!encontradas.length && video && /\.m3u8(\?|#|$)/i.test(video.currentSrc || '')) {
      encontradas = [{ url: video.currentSrc, t: 0 }];
    }
    if (!encontradas.length) {
      console.info('TDT local: todavía no veo ninguna lista .m3u8; espero ' + ESPERA_MS / 1000 + ' s (si el vídeo está parado, dale a reproducir)…');
      encontradas = await esperar(ESPERA_MS);
    }
    if (!encontradas.length) {
      console.warn('TDT local: no he visto ninguna lista .m3u8. Comprueba que el directo se está reproduciendo, o que es un directo HLS, y vuelve a pegar este archivo.');
      return;
    }
    const elegida = principal(encontradas);
    console.log('TDT local: listas .m3u8 vistas (la marcada con → es la que se ofrece):');
    encontradas.forEach((l, i) => console.log('  ' + (i + 1) + '. ' + (l === elegida ? '→ ' : '  ') + l.url));
    const enlace = enlaceTdt(PUERTO, elegida.url, nombreDe(document.title), location.hostname);
    try { if (typeof copy === 'function') copy(elegida.url); else navigator.clipboard.writeText(elegida.url); } catch (e) { /* no clipboard */ }
    console.log('TDT local: enlace copiado al portapapeles. Abriendo TDT local… si no se abre, usa este enlace:\n' + enlace);
    window.open(enlace, '_blank');
  }

  if (typeof module !== 'undefined' && module.exports) module.exports = { listas, principal, nombreDe, enlaceTdt };
  else main();
}());
