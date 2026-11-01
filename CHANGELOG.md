# Cambios

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/); el proyecto sigue
[SemVer](https://semver.org/lang/es/).

## [Sin publicar]

## [1.1.0] — 2026-11-01

Marcas de anuncios, reacciones a la publicidad, sonido (igualador y ecualizador) y Atresmedia con un clic.

### Correcciones
- Una petición `POST` rechazada (403) descarta ahora su cuerpo antes de responder, para que el cliente reciba el 403 en
  vez de un reinicio de conexión (visto en Windows).

### Funciones
- **Guía de la extensión del puente** en `tools/puente-atresplayer/LEEME.md`: para qué sirve, qué hace y qué no (sin
  permisos, solo dentro del reproductor, sin peticiones), instalación paso a paso, cómo comprobarla, problemas
  frecuentes, protocolo de mensajes y mantenimiento. El `manifest.json` pasa a la versión 1.1.0, la de TDT local.
- **Igualador de volumen y ecualizador en el reproductor de Atresplayer**: el puente (instalado como extensión) lleva
  ahora `audio-chain.js`, la cadena de sonido de la página generada con `scripts/build_bridge.py`, y la aplica dentro del
  reproductor con los ajustes del canal que le manda TDT local; el diálogo «Sonido» muestra la medida. Con solo el script
  pegado no hay procesado de sonido.
- **El anuncio de arranque del reproductor de Atresplayer no cambia de canal**: el que llega con menos de 20 s de programa
  seguidos antes (al pulsar «Directo» o cuando el reproductor se reinicia tras una pausa) solo silencia y avisa. Evita el
  bucle «Directo → anuncio → cambio de canal → volver → Directo». El puente cuenta ahora también si el reproductor emite.
- **Un canal, varias fuentes** al añadir canales propios: si ya existe uno con el mismo nombre, el enlace (o el reproductor
  de Atresplayer del botón «Atresmedia») se añade como otra fuente suya en vez de crear una copia. El reproductor incrustado
  va siempre después de los streams y no se recuerda como favorito, así que se prueba primero el stream y, si falla, el
  reproductor oficial. La API acepta `merge: true` en `/api/custom`.
- **El puente reconoce también el aviso de las pausas del directo** («El canal que estás viendo en directo se encuentra
  en estos momentos en publicidad»), además del «Publicidad» corto del anuncio previo; y dice en la consola qué texto vio.
- **Guía extra (XMLTV comunitario) e iconos para los canales de Atresmedia**: nuevos ajustes `epg_extra_enabled` y
  `epg_extra_source` (Listas y guía). Lee de una guía comunitaria solo los canales propios cuyo identificador no está en las
  guías de las listas, con ETag, cada 6 h como mucho y sin guardar el resto; el botón de Atresmedia la activa y da a esos
  canales su identificador y su icono. Volver a pulsarlo completa los canales ya añadidos.
- **Cambiar de canal durante la publicidad ya no destruye el original**: en vista simple el canal original sigue en otra
  casilla, fuera de la vista y silenciado. Así se ve cuándo acaba la pausa (marca de fin, o el aviso del puente de
  Atresplayer), se vuelve al instante y no se recarga, lo que arrancaba otro anuncio y otro cambio. En multivisión, un anuncio
  en los 90 s siguientes a volver a cargar un canal ya no provoca otro cambio.
- **Aviso fijo «PUBLICIDAD»** sobre la imagen mientras dura una pausa (opción nueva en «Durante la publicidad»), y
  **puente con el reproductor de Atresplayer**: `tools/puente-atresplayer`, una extensión (o script de usuario) que lee dentro
  del reproductor incrustado el aviso «Publicidad» y se lo cuenta a TDT local, que así puede avisar, reaccionar y silenciar
  el sonido (también con `M`). Sin el script nada cambia. La reacción ya no exige la vigilancia de marcas.
- **Atresmedia con un clic**: «Añadir canal» añade los canales de Atresmedia con el reproductor oficial incrustable de
  Atresplayer en una casilla (como YouTube; `frame-src` admite `https://www.atresplayer.com`; en multivisión solo se
  puede silenciar con el script del puente).
  Mediaset no se ofrece: Mediaset Infinity no permite incrustarse y sus canales ya están en las listas como «solo web».
  Un canal propio puede no tener enlace de stream si tiene web, y los canales propios se listan siempre.
- **Quitar canales propios desde la lista**: una ✕ en cada fila de canal propio, con confirmación; si el canal estaba en
  una casilla, esta se vacía.
  El aviso de «no se pudo reproducir» muestra ahora el código HTTP que devolvió el origen.
- **Sacar el enlace de un directo desde tu navegador**: `tools/capturar-directo.js`, un fragmento para la consola que
  toma de lo que ya se está reproduciendo la lista `.m3u8` y abre TDT local con el diálogo «Añadir canal» relleno
  (`#add=…`, solo rellena; el fragmento no sale del equipo y se borra de la barra de direcciones).
- **Marcas de anuncios (SCTE-35)**: vigilancia opcional que detecta, avisa y guarda en `data/scte.jsonl` las marcas de
  publicidad de los streams HLS (`CUE-OUT/IN`, `DATERANGE`, `OATCLS`…), decodifica el mensaje binario, y puede mirar
  también el PID SCTE-35 del MPEG-TS y los eventos `emsg`. Nueva pestaña en Ajustes, botón **Marcas** con el registro
  (descargable en JSON/CSV) y rutas `/api/scte*`.
- **Sonido**: igualador de volumen (sube lo bajo y baja lo alto hasta un nivel elegido, con tope de subida y limitador)
  y ecualizador de 10 bandas con preajustes, con ajustes globales y propios de cada canal. Cadena Web Audio por casilla,
  sin tocar el volumen ni el silencio existentes; el diálogo **Sonido** muestra la medida en vivo.
- **Durante la publicidad**: nueva pestaña en Ajustes para que la página reaccione cuando el canal que se ve entra en una
  pausa de anuncios: silenciar o bajar el sonido, cambiar a otro canal o mostrar una web sobre la imagen, volviendo al
  llegar la marca de fin o al pasar la duración. Respeta (o deshace, a elegir) lo que se toque durante la pausa. Nueva
  comprobación de que la web se puede mostrar (`/api/settings/test/web`); solo esa web se añade a `frame-src`.

## [1.0.0] — 2026-10-30

Primera versión publicable.

### Funciones
- Visor de la TDT española con las listas de TDTChannels y proxy HLS local.
- Radio (unas 980 emisoras) con reproducción directa o HLS.
- Comprobación de streams, favoritos y filtros.
- Multivisión de cuatro canales con rotación del audio.
- Guía de programación (XMLTV) con «ahora / después».
- Canales de YouTube incrustados y canales propios con cabeceras `Origin`/`Referer`.
- Asistente de IA local (API de chat compatible con OpenAI), con el razonamiento desactivado.
- Subtítulos en directo y alertas por voz con whisper.cpp.

### Ajustes
- Pantalla **Ajustes** con tres pestañas: asistente de IA (dirección, modelo, clave de API, temperatura, tokens,
  tiempo de espera, razonamiento y parámetros extra), subtítulos (idioma, modelo, carpeta de modelos, programa
  y servidor de Whisper, hilos, inactividad) y listas y guía (frecuencia, comprobación automática, guía y fuentes).
- Todo es persistente (`settings.json`) y se aplica sin reiniciar; lo fijado por flag o variable `TDT_<AJUSTE>` manda
  y se muestra bloqueado.
- Catálogo de modelos de Whisper con descarga (progreso, cancelación, comprobación de espacio y verificación
  SHA-256), «Probar conexión» del asistente y «Comprobar» de Whisper.
- Los ajustes solo se pueden cambiar desde el propio equipo, también con `--lan`.

### Distribución
- Instaladores para Windows (`.exe` y `.zip` portable), macOS (`.dmg`) y Linux (`.deb` y `.tar.gz`), con su propio Python.
- Aplicación de escritorio sin consola: datos por usuario, botón «Salir» y una sola instancia.
- Licencia Apache 2.0 con `NOTICE` y página «Créditos y licencias» (cita de TDTChannels, hls.js y el resto).
- Certificados TLS de reserva (sistema o certifi) para las aplicaciones empaquetadas.

### Calidad
- Reorganizado como paquete de Python (`tdtlocal/`) sin estado global, con instalación por
  `pyproject.toml` y `python -m tdtlocal`.
- Interfaz dividida en módulos ES; la lógica pura está en `static/js/lib/`.
- 252 pruebas de Python y 22 del navegador; CI en GitHub Actions; lint con ruff.
- Corregido: una respuesta del modelo que no era JSON devolvía «400 pregunta vacía» en lugar de un
  error de pasarela con un mensaje claro.
- Corregido: «pon el toro» no encontraba «El Toro TV».
- Corregido: tras reiniciar el servidor, los subtítulos de una casilla no se reanudaban.
- Mejorado: `/api/channels` ya no se retrasa varios segundos si Whisper no está en marcha.
- Los canales propios ya no pueden reutilizar el identificador de un canal de las listas.
- Los lanzadores ya no dependen de rutas personales: usan `iniciar.local.*` o variables `TDT_*`.
