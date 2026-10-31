# TDT local

[![CI](../../actions/workflows/ci.yml/badge.svg)](../../actions/workflows/ci.yml)

Visor web **local** para ver la TDT española y escuchar la radio en el PC sin las apps de cada
cadena. Usa las listas públicas de [TDTChannels](https://github.com/LaQuay/TDTChannels)
(`TELEVISION.md` y `RADIO.md`) y se actualiza solo. Solo biblioteca estándar de Python:
no hay nada que instalar con `pip`. El asistente de IA y los subtítulos son opcionales y usan
programas que ya tengas (un servidor llama.cpp, ffmpeg y whisper.cpp); sin ellos, todo lo demás
funciona igual.

> **In English:** a local web viewer for Spanish digital TV and radio, fed by the public
> [TDTChannels](https://github.com/LaQuay/TDTChannels) lists. Python standard library only; HLS
> playback through a local proxy, programme guide (XMLTV), 4-channel multi-view with rotating audio,
> optional local AI assistant (any OpenAI-compatible server such as llama.cpp) and live subtitles
> and voice alerts (whisper.cpp). The interface is in Spanish.

## Instalar

Descarga el instalador de tu sistema de la página de
[Releases](https://github.com/cibernicola/tdt-local/releases/latest) (incluye todo lo necesario, no hace falta Python): **Windows** `.exe` (o `.zip` portable), **macOS** `.dmg` (Intel o Apple Silicon), **Linux** `.deb` o `.tar.gz`.
Los paquetes no están firmados, así que Windows y macOS avisarán la primera vez: en
[docs/INSTALLERS.md](docs/INSTALLERS.md) está qué hacer, dónde guarda los datos y cómo se construyen.

## Arrancar desde el código

Hace falta Python 3.9 o superior.

- **Windows:** doble clic en `iniciar.bat`.
- **Linux / macOS:** `./iniciar.sh`
- **A mano:** `python -m tdtlocal --open`
- **Con pip:** `pip install .` y luego `tdt-local --open` (o `tdt-local-app`, la versión de escritorio)

Se abre `http://127.0.0.1:8788/`. Para cerrarlo, Ctrl+C en la ventana. La primera vez hace falta
conexión para descargar las listas; después se usa la última copia guardada en `data/`.

## Qué hace

- **Listas al día:** descarga las listas al arrancar y las revisa cada 6 h (con ETag, así que no
  baja nada si no han cambiado). Botón «Actualizar lista» para forzarlo.
- **Reproducción:** directos HLS con hls.js (incluido en `tdtlocal/static/vendor/`, sin CDN). Todo
  pasa por un proxy local (`/proxy`) porque casi ningún stream envía cabeceras CORS.
- **Radio:** selector «Televisión / Radio» (o `T`) con unas 980 emisoras. mp3/aac/«stream» van
  directos al reproductor del navegador y las de m3u8 con hls.js. Se muestra el logo en lugar de vídeo.
- **Comprobar canales:** pide a cada stream su lista, una variante y el último segmento (en radio,
  los primeros bytes de audio) y marca cada uno en verde o rojo. «Ocultar caídos» los filtra.
- **Multivisión** (`V`): cuatro canales a la vez; solo suena la casilla activa. Clic en una casilla
  (o `← →`) le pasa el audio. «Cuadrícula» reparte 2×2 y «Foco» agranda la activa. «Rotar» pasa el
  audio a la siguiente casilla cada 10–60 s.
- **Guía de programación (EPG):** descarga cada hora los XMLTV de TDTChannels y los casa con la
  columna «EPG ID». Muestra el programa en emisión y el siguiente; `G` abre la programación completa
  del canal activo. Cubre unos 175 canales de tele y unas 50 emisoras; `--no-epg` la desactiva.
- **YouTube:** los canales cuyo directo es una página de YouTube se reproducen con el reproductor
  oficial incrustado, también en el mosaico. No pasan por el proxy.
- **Canales propios:** «Añadir canal» guarda un enlace que pegues tú (m3u8, mp3/aac o YouTube) en
  `data/custom.json`, con cabeceras `Origin`/`Referer` opcionales que el proxy envía con la lista y
  con cada segmento. Hay un preset para Atresplayer. No se salta DRM ni geobloqueos: solo cabeceras.
- **Asistente de IA** (`Ctrl+K`): órdenes como «pon La 2» o «pon La 2, TRECE y El Toro en
  multivisión rotando cada 30 s» se resuelven al instante en el navegador; el resto («hay fútbol
  ahora») va a tu modelo local, que solo recibe unas decenas de canales preseleccionados y no puede
  ejecutar nada que no esté en esa lista. Usa la API de chat de OpenAI de llama.cpp (`--llm-url`).
- **Subtítulos en directo** (`U`) y **alertas por voz**: ffmpeg saca el audio y `whisper-server`
  (whisper.cpp) lo transcribe en tu equipo; el audio no sale de él. Las alertas vigilan palabras en
  las cuatro casillas y, al oír una, resaltan la casilla y le pasan el audio.
- Favoritos, último canal, volumen, filtros, mosaico y rotación se guardan en el navegador. Los
  logos se descargan una vez a `data/logos/`.

## Teclas

| Tecla | Acción |
|---|---|
| 0–9, Intro | ir al número de canal (el de la lista visible) |
| Re Pág / Av Pág, ↑ ↓ | canal anterior / siguiente |
| S · F · M · P · / | favorito · pantalla completa · silencio · ventana flotante · buscar |
| T · V · C · G | televisión/radio · multivisión · ocultar/mostrar la lista · guía |
| ← → · R | multivisión: cambiar de casilla activa · activar/parar la rotación |
| U · Ctrl+K | subtítulos en directo · asistente de IA |

## Ajustes

El botón **Ajustes** (abajo, en el panel de canales) abre la configuración. Todo se guarda en
`settings.json`, dentro de la carpeta de datos, y se aplica al momento, sin reiniciar.

- **Asistente de IA:** activarlo, dirección del servidor (API compatible con OpenAI, p. ej. llama.cpp o un servicio
  en línea), modelo (con «Probar conexión» se listan los que ofrece el servidor), clave de API opcional (se guarda en
  tu equipo y no se vuelve a mostrar), temperatura, máximo de tokens, tiempo de espera, pedir al modelo que no
  «piense» y parámetros extra en JSON (`top_p`, `top_k`…).
- **Subtítulos y alertas:** activarlos, idioma (o detección automática), modelo, carpeta de modelos, programa
  `whisper-server`, dirección del servidor, arranque automático, hilos y minutos de inactividad. Incluye un
  catálogo para **descargar modelos** de Whisper con progreso, cancelación y verificación SHA-256, y un botón
  «Comprobar» que dice qué falta (ffmpeg, el programa, el modelo, el servidor).
- **Listas y guía:** cada cuántas horas se actualizan, comprobar los streams tras actualizar, guía de programación
  y, en «avanzado», las cuatro direcciones de origen.

Los ajustes solo se pueden cambiar desde el propio equipo (aunque uses `--lan`): `whisper-server` es un programa
que se ejecuta y no debe poder elegirlo cualquiera de tu red.

### Línea de comandos y variables de entorno

Lo que fijes por línea de comandos o con una variable `TDT_<AJUSTE>` manda sobre lo guardado: en Ajustes aparece
bloqueado y no se escribe en `settings.json`. Útil para scripts, contenedores o para no guardar una clave en disco
(`TDT_LLM_API_KEY`). Orden de prioridad: valores por defecto, lo guardado en Ajustes, y por último flag o variable.

```
--port 8788           puerto
--host ADDR           dirección donde escuchar (127.0.0.1)
--lan                 escuchar en toda la red local (tablet, móvil...), SIN autenticación
--open                abrir el navegador
--verbose             registrar cada petición HTTP
--quit-button         mostrar el botón «Salir», que cierra el servidor (lo usa la app de escritorio)
--data-dir DIR        carpeta de datos (por defecto ./data, o la carpeta de usuario si está instalado)
--interval HORAS      horas entre actualizaciones de la lista (6)
--auto-check          comprobar los streams de la tele tras cada actualización
--source URL          otra copia de TELEVISION.md
--radio-source URL    otra copia de RADIO.md
--epg-source URL      otro XMLTV (.xml o .xml.gz) para la tele
--radio-epg-source URL  otro XMLTV para la radio
--no-epg              no descargar la guía de programación
--llm-url URL         servidor de IA compatible con OpenAI (por defecto http://127.0.0.1:8080/v1)
--llm-model NAME      nombre del modelo, si tu servidor lo exige
--no-ai               desactivar el asistente
--models-dir DIR      carpeta de los modelos de Whisper
--whisper-url URL     whisper-server (por defecto :8178); si no responde, se lanza uno
--whisper-bin PATH    whisper-server (por defecto, el del PATH)
--whisper-model PATH  modelo ggml (por defecto, el primero de la carpeta de modelos)
--whisper-lang es     idioma del audio (o auto)
--no-stt              desactivar subtítulos y alertas
--version
```

Cualquier ajuste tiene su variable: el nombre del ajuste en mayúsculas con prefijo `TDT_` (`TDT_LLM_URL`,
`TDT_LLM_API_KEY`, `TDT_WHISPER_BIN`, `TDT_WHISPER_THREADS`, `TDT_STT_ENABLED=0`…). Los nombres están en
[`tdtlocal/settings.py`](tdtlocal/settings.py). `TDT_DATA_DIR` fija la carpeta de datos. En los lanzadores puedes
ponerlas en `iniciar.local.bat` / `iniciar.local.sh`, que no se suben a git.

### Subtítulos con Whisper

1. Instala [ffmpeg](https://ffmpeg.org/) y deja `ffmpeg` en el `PATH`.
2. Compila o descarga [whisper.cpp](https://github.com/ggml-org/whisper.cpp) y pon `whisper-server` en el `PATH`,
   o indica su ruta en Ajustes ➜ Subtítulos (o con `--whisper-bin`).
3. En Ajustes ➜ Subtítulos, elige un modelo del catálogo y pulsa **Descargar** (por ejemplo `large-v3-turbo-q5_0`,
   574 MB, el recomendado con GPU). Pulsa **Comprobar** para confirmar que todo está en su sitio.

Si no hay un `whisper-server` en marcha, TDT local lanza uno y lo apaga tras unos minutos sin uso.

## Seguridad

TDT local es una herramienta **personal para tu propio equipo**.

- Por defecto solo escucha en `127.0.0.1` y rechaza peticiones cuyo `Host` no sea local
  (protege frente a DNS rebinding), de otro origen (`Sec-Fetch-Site`, `Origin`) o con rutas fuera
  de `tdtlocal/static/`.
- El proxy solo acepta hosts que salen de las listas (o de redirecciones de streams ya validados),
  solo `http(s)`, y rechaza siempre direcciones no públicas (loopback, red local, metadatos de la
  nube).
- Cabecera `Content-Security-Policy` estricta: sin scripts ni estilos en línea.
- El modelo de IA no es de fiar: sus respuestas se validan y solo se aceptan acciones y canales
  de la lista que se le ofreció.
- `--lan` abre la app a toda tu red local **sin autenticación**: úsalo solo en redes de confianza.

Para avisar de un problema de seguridad, mira [SECURITY.md](SECURITY.md).

## Límites

- Hay canales sin directo abierto en la lista (p. ej. Cuatro y Telecinco): salen como «solo web» y
  se ofrece el enlace a su página. No se intenta saltar ningún DRM ni geobloqueo.
- Los streams cambian de URL a menudo. Si uno falla, prueba la otra fuente (botones 1, 2…) o
  actualiza la lista.
- Whisper falla con música y con emisiones fMP4/CMAF; cada casilla transcrita gasta algo de GPU.
- Si cierras el servidor a la fuerza (sin Ctrl+C) puede quedar un `whisper-server` huérfano.
- Si la lista descargada trae menos de 50 canales (30 en radio) se descarta y se conserva la
  anterior, por si el formato del repositorio de origen cambia.
- Los logos de `graph.facebook.com` de la lista ya no cargan; se muestran las iniciales.

## Desarrollo

```
python -m unittest discover -s tests -t .            # pruebas de Python (sin dependencias)
node --test                                           # pruebas del código del navegador (Node 20+)
python scripts/check.py                               # todo lo anterior y el lint, si está instalado
pip install ruff pytest && ruff check . && ruff format --check .
```

La arquitectura está en [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) y la guía para contribuir en
[CONTRIBUTING.md](CONTRIBUTING.md). Los cambios están en [CHANGELOG.md](CHANGELOG.md) y lo que
falta por hacer, en [ROADMAP.md](ROADMAP.md).

```
tdtlocal/            paquete de Python (servidor, proxy, EPG, IA, transcripción)
tdtlocal/static/     interfaz: index.html, style.css y módulos ES en js/ (lib/ = lógica pura)
tdtlocal/static/vendor/  hls.js (Apache-2.0, con su licencia)
packaging/           PyInstaller, Inno Setup, .dmg, .deb y el script de construcción de instaladores
tests/               pruebas de Python (tests/*.py) y del navegador (tests/js/)
docs/                documentación técnica
data/                (se crea solo, no se versiona) listas, estado, logos y canales propios
models/              (no se versiona) modelo de Whisper
```

## Créditos, licencia y aviso

- Las listas de canales y las guías son de [TDTChannels](https://github.com/LaQuay/TDTChannels)
  (Apache-2.0; las guías las sirven tdtchannels.com y [Onda Channels](https://www.ondachannels.com/) y están sujetas a su
  [aviso legal](https://www.tdtchannels.com/aviso-legal/)). Sin su trabajo esto no existiría.
- [hls.js](https://github.com/video-dev/hls.js) (Apache-2.0, © Dailymotion) reproduce el HLS en el navegador.
- Opcionales y no incluidos: [llama.cpp](https://github.com/ggml-org/llama.cpp) (MIT),
  [whisper.cpp](https://github.com/ggml-org/whisper.cpp) (MIT) y [FFmpeg](https://ffmpeg.org) (LGPL/GPL).
- Los instaladores incluyen el intérprete de Python (licencia PSF) y se construyen con PyInstaller.
- TDT local no aloja ni redistribuye ningún contenido: es un reproductor que enlaza los directos que
  las propias cadenas publican abiertamente. Los canales y su contenido pertenecen a sus titulares.

### Licencia

[Apache License 2.0](LICENSE). Es libre: puedes usarlo, modificarlo y redistribuirlo, incluso con fines
comerciales, **a condición de citar su origen**: conserva el aviso de copyright, el fichero [NOTICE](NOTICE) (con la cita de
TDTChannels, hls.js y el resto) y marca los cambios que hagas. Los créditos también salen en la propia aplicación,
en «Créditos y licencias». Detalle de las licencias de terceros en [NOTICE](NOTICE).
