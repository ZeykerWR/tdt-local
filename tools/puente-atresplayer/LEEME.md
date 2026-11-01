# Puente de TDT local con el reproductor de Atresplayer

Una extensión pequeña para tu navegador que deja a TDT local **enterarse de la publicidad** del reproductor de
Atresplayer y **controlar su sonido**. Es opcional: sin ella los canales de Atresmedia se ven igual, pero TDT local no
puede saber qué pasa dentro de su reproductor.

## Para qué sirve

El botón **Atresmedia** de «Añadir canal» pone el reproductor oficial de Atresplayer dentro de una casilla de TDT local,
igual que se hace con YouTube. Ese reproductor es de **otro origen** (`atresplayer.com`): el navegador no deja que la
página de TDT local lea lo que pasa dentro ni toque su sonido, y el reproductor no avisa hacia fuera. Un trozo de código
que se ejecute *dentro* del reproductor sí puede, y eso es esta extensión.

Con ella instalada, TDT local puede:

| Función | Qué hace |
|---|---|
| **Detectar la publicidad** | Lee el aviso que el propio reproductor te enseña («Publicidad» o «El canal que estás viendo en directo se encuentra en estos momentos en publicidad») y se lo cuenta a TDT local. |
| **Reaccionar** | TDT local muestra su rótulo «PUBLICIDAD», cambia de canal o abre una web, según lo que hayas elegido en **Ajustes ▸ Durante la publicidad**. |
| **Silenciar** | Silencia el reproductor durante la pausa, con la tecla `M`, y en multivisión deja sonar solo la casilla activa. |
| **Igualar el volumen y ecualizar** | Aplica dentro del reproductor la misma cadena de sonido de TDT local (diálogo **Sonido**), con los ajustes globales o los del canal. |

## Lo que NO hace

- No hace peticiones de red ni descarga nada.
- No toca, salta ni bloquea la publicidad: solo lee el aviso que ya se ve en pantalla.
- No lee nada que no estés viendo, ni tus cookies, ni tu cuenta, ni el resto de tus pestañas.
- No pide **ningún permiso** (el `manifest.json` no declara `permissions` ni `host_permissions`).
- Solo se ejecuta en `https://www.atresplayer.com/embed/live/*` y `/embed/video/*` (y las mismas rutas sin `www`), es
  decir, dentro del reproductor incrustado del directo o de una grabación; no en el resto de Atresplayer ni en otras webs.
- Solo habla con la página que incrusta el reproductor, y solo si es TDT local (`127.0.0.1`, `localhost` o `[::1]`).
  Si el reproductor está incrustado en otra página, el puente no hace nada.

El código es corto y está sin empaquetar para que lo puedas leer: `puente.user.js` (unas 190 líneas) y `audio-chain.js`
(la cadena de sonido, generada).

## Instalarla (Chrome, Edge, Brave y otros basados en Chromium)

Hazlo en **el navegador donde abres TDT local**.

1. Abre `chrome://extensions` (en Brave `brave://extensions`, en Edge `edge://extensions`).
2. Activa el **Modo de desarrollador** (arriba a la derecha).
3. Pulsa **Cargar descomprimida** y elige la carpeta **entera** `tools/puente-atresplayer` (la que tiene
   `manifest.json`, no uno de los archivos sueltos). Sin `audio-chain.js` solo habría detección y silencio, no igualador
   ni ecualizador.
4. Recarga la página de TDT local.

Chrome puede avisar al arrancar de que hay extensiones de modo desarrollador sin publicar: es lo esperado, porque esta
extensión no está en ninguna tienda. Para quitarla, usa el botón **Quitar** de la misma pantalla.

> **Firefox:** esta extensión es de Manifest V3 para Chromium. En Firefox usa la alternativa del apartado siguiente
> (sin igualador ni ecualizador).

## Alternativa: solo como script de usuario

Si prefieres Tampermonkey o Violentmonkey, crea un script nuevo y pega `puente.user.js`. En las versiones recientes de
Chrome, Edge y Brave esas extensiones piden además activar **«Permitir scripts de usuario»** en sus detalles. Así hay
**detección de publicidad y silencio, pero no igualador ni ecualizador**, porque `audio-chain.js` no va incluido.

## Cómo saber que funciona

1. En TDT local, abre un canal de Atresmedia.
2. Bajo el nombre del canal debe aparecer **«puente activo»**. Si a los 6 segundos no ha dado señales, dice
   **«puente no detectado»**.
3. En el diálogo **Sonido** (con un canal de Atresplayer activo), la línea de medida muestra «Esperando la medida del
   puente» al principio y después «Ahora mismo (dentro de Atresplayer)…». Si se queda en «Esperando…», lo que tienes
   instalado no es la extensión completa.
4. Con F12 ▸ Consola, mira los mensajes que empiezan por **«[TDT puente]»**: «script cargado en…», «activo dentro de
   http://127.0.0.1:…», «publicidad: empieza (…)» y «publicidad: termina».

## Si no funciona

| Síntoma | Causa probable |
|---|---|
| «puente no detectado» | La extensión no está cargada o está desactivada, o no recargaste TDT local después de instalarla. Si usas el script de usuario, falta «Permitir scripts de usuario». |
| Detecta la publicidad pero el diálogo **Sonido** no mide | Cargaste solo el script, o la carpeta sin `audio-chain.js`. Carga la carpeta entera. |
| No procesa el sonido hasta hacer clic | El navegador solo deja procesar audio tras una primera interacción con la página. Haz clic en cualquier sitio. |
| Hay publicidad y no se entera | El reproductor mostró otro texto. Mira la consola: si no sale «publicidad: empieza», añade el texto nuevo a la lista `FRASES` de `puente.user.js`. |
| El reproductor dice que no se pudo reproducir | No es del puente: el reproductor oficial puede negarse según la red o la cuenta (por ejemplo con VPN). Prueba la URL del reproductor en una pestaña. |
| Quieres comprobar que el código se ejecuta | Pega `puente.user.js` en la consola, eligiendo en el desplegable «top» el contexto de `atresplayer.com`. Solo comprueba que corre; no lo deja conectado a la casilla. |

## Cómo funciona (para quien quiera mirarlo)

TDT local y la extensión se hablan con `postMessage`, y cada lado comprueba quién le escribe.

- Del reproductor a TDT local (`source: "tdt-bridge"`):
  - `ready`: el puente ha arrancado.
  - `state`: `{ ad, playing }`, si hay publicidad y si el reproductor está emitiendo. Se repite cada 4 s y cuando cambia;
    `playing` sirve para distinguir el anuncio de arranque (al pulsar «Directo») de una pausa del directo.
  - `meter`: `{ loudness, gainDb }`, lo que oye y corrige el igualador, cada 0,5 s.
- De TDT local al reproductor (`source: "tdt-local"`):
  - `audio`: `{ muted, volume }`.
  - `fx`: `{ level, eq }`, los ajustes de igualador y ecualizador del canal.

El puente solo acepta mensajes de la ventana que lo incrusta (`window.parent`) y, cuando el navegador dice su origen
(`location.ancestorOrigins`), solo de ese origen. Para detectar la publicidad busca en el texto visible del reproductor
una de las frases de `FRASES`, y solo si es corta, de modo que el título de un programa que mencione la publicidad no
cuenta. Para el sonido engancha un `AudioContext` al `<video>` del reproductor y aplica la misma cadena que usa la
página (medida K-weighted, igualador de 10 bandas y limitador).

## Mantenimiento

`audio-chain.js` **no se edita a mano**: se genera a partir del código de la página (`tdtlocal/static/js/lib/audio.js` y
`tdtlocal/static/js/audio.js`).

```bash
python scripts/build_bridge.py          # lo regenera
python scripts/build_bridge.py --check  # solo comprueba si está al día
```

Una prueba (`tests/test_bridge_build.py`) y `scripts/check.py` fallan si se queda desfasado. El protocolo de mensajes
está en `tdtlocal/static/js/lib/bridge.js` y una prueba comprueba que el `manifest.json` no pide permisos y solo
incluye los dos archivos esperados.

## Estado

Probada con el reproductor real de Atresplayer para detectar la publicidad y con páginas de prueba para el sonido. El
procesado de sonido dentro del reproductor real, ya cargada como extensión, está **poco probado**. Mediaset no tiene
puente de momento: su reproductor no se puede incrustar.
