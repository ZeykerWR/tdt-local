// ==UserScript==
// @name         TDT local · puente con el reproductor de Atresplayer
// @namespace    https://github.com/cibernicola/tdt-local
// @version      1.2.0
// @description  Cuenta a TDT local cuándo el reproductor incrustado de Atresplayer muestra «Publicidad», y le deja silenciarlo.
// @match        https://www.atresplayer.com/embed/live/*
// @match        https://atresplayer.com/embed/live/*
// @match        https://www.atresplayer.com/embed/video/*
// @match        https://atresplayer.com/embed/video/*
// @run-at       document-idle
// @grant        none
// ==/UserScript==

// Para qué sirve: el reproductor de Atresplayer que TDT local muestra dentro de una casilla es de otro origen, y el navegador
// no deja que TDT local vea lo que pasa dentro. Este script se ejecuta DENTRO de ese reproductor, lee el aviso «Publicidad»
// que el propio reproductor ya te enseña y se lo cuenta a TDT local con un mensaje (`postMessage`). Con eso TDT local puede
// mostrar su aviso, cambiar de canal o abrir una web, y también silenciar el sonido del reproductor mientras dura la publicidad.
//
// Qué NO hace: no hace peticiones, no toca la publicidad ni la salta, no lee nada que no estés viendo y no manda nada
// fuera de tu navegador. Solo habla con la página de TDT local que tiene este reproductor dentro (en Chrome, Edge y Brave se
// comprueba que es 127.0.0.1 o localhost; en Firefox no se puede comprobar, y solo obedece a la página que lo incrusta).
//
// Sonido: además, si el puente se instala como EXTENSIÓN (la carpeta entera, con audio-chain.js), TDT local aplica dentro del
// reproductor su igualador de volumen y su ecualizador, con los ajustes del canal. El script pegado solo (Tampermonkey o
// consola) no lleva esa parte: silencia y avisa de la publicidad, pero no iguala ni ecualiza.
//
// Tres formas de ponerlo en marcha (en el navegador donde abres TDT local):
//  1. EXTENSIÓN (la más sencilla, sin gestor de scripts): esta misma carpeta es una extensión. En brave://extensions,
//     chrome://extensions o edge://extensions activa el «Modo de desarrollador», pulsa «Cargar descomprimida» y elige la
//     carpeta tools/puente-atresplayer. No pide permisos. (Chrome avisa al arrancar de que hay extensiones sin publicar.)
//  2. GESTOR DE SCRIPTS: instala Tampermonkey o Violentmonkey, crea un script nuevo y pega todo este archivo. En las
//     versiones recientes de Chrome, Edge y Brave la extensión pide además activar «Permitir scripts de usuario» en sus
//     detalles y, según la versión, el modo de desarrollador.
//  3. PRUEBA SUELTA: con TDT local abierto en un canal de Atresmedia, F12 ▸ Consola, elige en el desplegable «top» el
//     contexto de atresplayer.com y pega todo este archivo. Vale hasta que recargues la página.
//
// Comprobación: en TDT local, la línea bajo el nombre del canal dirá «puente activo». Si dice «puente no detectado», el
// script no está corriendo dentro del reproductor; abre la consola (F12) y busca mensajes que empiecen por «[TDT puente]».

// Qué mira: dos textos del propio reproductor, visibles en la parte de arriba. El corto «Publicidad» (el anuncio que sale al
// pulsar «Directo») y el aviso «El canal que estás viendo en directo se encuentra en estos momentos en publicidad» (las
// pausas del directo). Desaparecen al terminar. Si el reproductor usa otro texto, añádelo a FRASES, más abajo.
(function () {
  'use strict';

  // What the player shows while an ad break lasts. Two texts are known: the short label «Publicidad» (the ad that comes
  // before «Directo», and over the ads), and the notice «El canal que estás viendo en directo se encuentra en estos
  // momentos en publicidad» of the breaks of the live channel. Only these, and short: a programme title or a description
  // that mentions advertising must not count. Add a line here if the player shows another one.
  const FRASES = [
    { re: /^publicidad\b/i, max: 40 }, // "Publicidad", "Publicidad · 0:30"…
    { re: /\b(se encuentra|está) en (estos momentos|este momento) en publicidad\b/i, max: 160 },
  ];
  const LATIDO_MS = 4000;
  const LOOPBACK = /^https?:\/\/(127\.0\.0\.1|localhost|\[::1\])(:\d+)?$/i;

  /** Is this one of the texts the player shows while an ad break lasts? */
  const esEtiquetaDePublicidad = (texto) => {
    const limpio = String(texto || '').trim();
    return limpio.length > 0 && FRASES.some((f) => limpio.length <= f.max && f.re.test(limpio));
  };

  /** Can the page that embeds this player be TDT local? `undefined` when the browser does not say (Firefox). */
  const esTdtLocal = (origen) => (origen ? LOOPBACK.test(origen) : undefined);

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { esEtiquetaDePublicidad, esTdtLocal };
    return;
  }
  const traza = (...cosas) => console.info('[TDT puente]', ...cosas);
  traza('script cargado en', location.href);
  if (window.parent === window) { // opened alone, not inside TDT local
    traza('esta página no está dentro de TDT local: aquí el puente no hace nada (si ves este mensaje, el script sí se ejecuta)');
    return;
  }

  const origenPadre = (location.ancestorOrigins && location.ancestorOrigins[0]) || '';
  if (esTdtLocal(origenPadre) === false) { // embedded by some other page: it gets nothing, and gives no orders
    traza('la página que incrusta este reproductor es', origenPadre, '(no 127.0.0.1 ni localhost): el puente no hace nada');
    return;
  }
  const destino = origenPadre || '*';
  traza('activo dentro de', origenPadre || '(origen desconocido)');

  const visible = (el) => {
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) return false;
    const css = getComputedStyle(el);
    return css.visibility !== 'hidden' && css.display !== 'none' && Number(css.opacity) > 0.05;
  };

  /** The text that says there is an ad break, or `''`. */
  function textoDePublicidad() {
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    for (let nodo = walker.nextNode(); nodo; nodo = walker.nextNode()) {
      if (esEtiquetaDePublicidad(nodo.nodeValue) && nodo.parentElement && visible(nodo.parentElement)) return nodo.nodeValue.trim();
    }
    return '';
  }

  const decir = (mensaje) => window.parent.postMessage({ source: 'tdt-bridge', ...mensaje }, destino);

  /** Is the player emitting something (programme or ad)? TDT local uses it to tell the start-up ad from a break. */
  const reproduciendo = () => [...document.querySelectorAll('video')].some((v) => !v.paused && !v.ended && v.readyState >= 2);

  let ultimo = null; // what was last said
  let silenciar = false; // what TDT local last asked for
  function comprobar(forzar) {
    const texto = textoDePublicidad();
    const ahora = texto !== '';
    if (forzar || ahora !== ultimo) {
      if (ahora !== ultimo) traza(ahora ? 'publicidad: empieza (' + texto + ')' : 'publicidad: termina');
      ultimo = ahora;
      decir({ type: 'state', ad: ahora, playing: reproduciendo() });
    }
  }

  function aplicarAudio() {
    for (const medio of document.querySelectorAll('video, audio')) {
      if (silenciar && !medio.muted) medio.muted = true; // only to silence it: giving the sound back is up to the player
    }
  }

  // the player makes its <video> when «Directo» is pressed: if TDT local asked for silence, it starts silenced
  for (const tipo of ['play', 'playing', 'loadedmetadata', 'volumechange']) {
    document.addEventListener(tipo, () => { if (silenciar) aplicarAudio(); }, true);
  }

  // ---- sound: the leveler and the equalizer of TDT local, inside the player. Only when the extension loads
  // audio-chain.js (a copy of the page's sound chain, made by scripts/build_bridge.py); the pasted script alone has none.
  let sonido = null; // what TDT local last asked for: {level, eq}
  const cadenas = new WeakMap();
  let ultimaCadena = null;

  function aplicarSonido() {
    const audio = window.TDT_AUDIO;
    if (!audio || !sonido) return;
    const necesita = sonido.level.on || sonido.eq.on;
    for (const medio of document.querySelectorAll('video, audio')) {
      let cadena = cadenas.get(medio);
      if (!cadena && necesita) {
        cadena = audio.chainFor(medio); // null until the audio context runs (it needs the page to have had a click)
        if (cadena) cadenas.set(medio, cadena);
        else audio.wake().then(aplicarSonido);
      }
      if (cadena) {
        cadena.configure(sonido);
        ultimaCadena = cadena;
      }
    }
  }

  // the player makes its <video> when «Directo» is pressed: the sound chain goes onto it as soon as it exists
  for (const tipo of ['play', 'playing', 'loadedmetadata']) document.addEventListener(tipo, aplicarSonido, true);

  window.addEventListener('message', (e) => {
    if (e.source !== window.parent) return;
    if (origenPadre && e.origin !== origenPadre) return;
    const d = e.data;
    if (!d || typeof d !== 'object' || d.source !== 'tdt-local') return;
    if (d.type === 'fx' && window.TDT_AUDIO) {
      sonido = window.TDT_AUDIO.sanitize({ global: { level: d.level, eq: d.eq }, channels: {} }).global;
      aplicarSonido();
    }
    if (d.type === 'audio') {
      const quitar = silenciar && !d.muted;
      silenciar = !!d.muted;
      for (const medio of document.querySelectorAll('video, audio')) {
        if (silenciar) medio.muted = true;
        else if (quitar) medio.muted = false;
        if (typeof d.volume === 'number' && d.volume >= 0 && d.volume <= 1) medio.volume = d.volume;
      }
    }
  });

  let pendiente = 0;
  new MutationObserver(() => {
    clearTimeout(pendiente);
    pendiente = setTimeout(() => comprobar(false), 250);
  }).observe(document.body, { childList: true, subtree: true, characterData: true, attributes: true });

  decir({ type: 'ready', version: 1 });
  comprobar(true);
  setInterval(() => { comprobar(true); aplicarAudio(); aplicarSonido(); }, LATIDO_MS);
  setInterval(() => { // what the leveler hears and does, for the "Sonido" dialog
    if (!ultimaCadena || !sonido || !(sonido.level.on || sonido.eq.on)) return;
    const lectura = ultimaCadena.readout();
    decir({ type: 'meter', loudness: Number.isFinite(lectura.loudness) ? lectura.loudness : null, gainDb: lectura.gainDb });
  }, 500);
}());
