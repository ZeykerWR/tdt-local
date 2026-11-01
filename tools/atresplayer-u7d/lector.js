// Para qué sirve: Atresplayer publica en una página pública por canal («Emitido en TV (U7D)», por ejemplo
// https://www.atresplayer.com/antena3/u7d/) lo emitido en la última semana. La página se monta en el navegador, así que
// solo se puede leer desde dentro de ella. Este script, que TDT local carga como plugin en la ventana «Explorar
// Atresplayer», lee de esa página los enlaces de grabaciones (/grabaciones/<canal>/<id>/) con su título, día y hora, y se
// los cuenta a TDT local para que los reproduzca con el reproductor oficial incrustado de Atresplayer.
//
// Qué NO hace: no hace peticiones, no inicia sesión, no pulsa nada, no toca el aviso de cookies y no lee nada fuera de
// esa página. Lo único que hace además de leer es desplazar la página hacia abajo unas pocas veces (como harías tú) para
// que la propia web cargue las filas siguientes, y luego la deja arriba.
(function () {
  'use strict';

  const HREF = /^\/grabaciones\/([a-z0-9-]{2,40})\/([0-9a-f]{24})\/?$/i;
  const DIA = /^(lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo)\s+(\d{1,2})$/i;
  const HORA = /^(\d{1,2}):(\d{2})$/;
  const IMAGEN = /^https:\/\/imagenes\.atresplayer\.com\//;
  const MAX_ITEMS = 200;

  /**
   * Una tarjeta de la página como programa, o `null` si no es una grabación.
   * @param {{href: string, title?: string, aria?: string, lines?: string[], image?: string}} card
   */
  function leerTarjeta(card) {
    const m = HREF.exec(String(card.href || ''));
    if (!m) return null;
    const lines = (card.lines || []).map((l) => String(l).trim()).filter(Boolean);
    const dia = lines.map((l) => DIA.exec(l)).find(Boolean);
    const hora = lines.map((l) => HORA.exec(l)).find(Boolean);
    const aria = String(card.aria || '').replace(/\.\s*[^.]*$/, '').trim(); // «El secreto. Antena 3» -> «El secreto»
    const title = String(card.title || '').trim() || aria || lines.filter((l) => !DIA.test(l) && !HORA.test(l)).pop() || '';
    if (!title) return null;
    return {
      id: m[2].toLowerCase(),
      channel: m[1].toLowerCase(),
      title: title.slice(0, 160),
      day: dia ? Number(dia[2]) : 0,
      time: hora ? hora[1].padStart(2, '0') + ':' + hora[2] : '',
      image: IMAGEN.test(card.image || '') ? card.image : '',
    };
  }

  /** Todas las tarjetas distintas de una lista de enlaces, en el orden en que salen. */
  function leerTarjetas(cards) {
    const seen = new Set();
    const out = [];
    for (const card of cards) {
      const item = leerTarjeta(card);
      if (!item || seen.has(item.id)) continue;
      seen.add(item.id);
      out.push(item);
      if (out.length >= MAX_ITEMS) break;
    }
    return out;
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { leerTarjeta, leerTarjetas };
    return;
  }

  const slug = location.pathname.split('/').filter(Boolean)[0] || '';
  const decir = (mensaje) => window.postMessage({ source: 'tdt-u7d', slug, ...mensaje }, location.origin);

  function leer() {
    const cards = [...document.querySelectorAll('a[href^="/grabaciones/"]')].map((a) => {
      const img = a.querySelector('img.row-item--image') || a.querySelector('img');
      return {
        href: a.getAttribute('href'),
        title: a.getAttribute('title'),
        aria: a.getAttribute('aria-label'),
        lines: (a.innerText || '').split('\n'),
        image: img ? img.currentSrc || img.src : '',
      };
    });
    return leerTarjetas(cards);
  }

  let ultimo = '';
  function contar() {
    const items = leer();
    const huella = items.map((i) => i.id + (i.image ? '+' : '')).join(','); // también cuando llega una imagen
    if (items.length && huella !== ultimo) {
      ultimo = huella;
      decir({ type: 'items', items });
    }
    return items.length;
  }

  let pendiente = 0;
  new MutationObserver(() => {
    clearTimeout(pendiente);
    pendiente = setTimeout(contar, 800);
  }).observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['src'] });

  // la página trae unas filas y carga el resto al llegar abajo: se baja unas pocas veces y se vuelve arriba
  async function recorrer() {
    const pausa = (ms) => new Promise((r) => setTimeout(r, ms));
    for (let i = 0; i < 40 && !contar(); i++) await pausa(500); // espera a que la página pinte la primera fila
    for (let i = 0; i < 5; i++) {
      window.scrollTo(0, document.body.scrollHeight);
      await pausa(1500);
      contar();
    }
    window.scrollTo(0, 0);
    await pausa(1000);
    contar();
    decir({ type: 'done', count: leer().length });
  }

  if (document.readyState === 'complete') recorrer();
  else window.addEventListener('load', recorrer, { once: true });
}());
