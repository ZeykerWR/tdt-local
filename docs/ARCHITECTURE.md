# Arquitectura

TDT local son dos mitades que hablan por HTTP en `127.0.0.1`: un servidor de Python (solo biblioteca
estándar) y una interfaz de módulos ES sin *bundler*. No hay base de datos: el estado vive en
memoria y se persiste en JSON bajo `data/`.

```
navegador ──HTTP──▶ server.Handler ──▶ App ─┬─ Store        estado + persistencia (data/*.json)
   │                    │                   ├─ Net          descarga con lista de hosts permitidos
   │  /proxy ───────────┤                   ├─ FeedSyncer   TELEVISION.md / RADIO.md  ─▶ parser
   │  /api/*            │                   ├─ EpgSyncer    XMLTV ─▶ guía "ahora / después"
   │  estáticos         │                   ├─ HealthChecker comprobación de streams
   ▼                    │                   ├─ Assistant    llama.cpp (API de chat OpenAI)
 hls.js / <video>       │                   ├─ Transcriber  ffmpeg + whisper-server
                        │                   └─ LogoCache    logos en disco
                        └─ Tap ──▶ Transcriber (copia de los segmentos que pasan por el proxy)
```

## Paquete `tdtlocal/`

| Módulo | Responsabilidad |
|---|---|
| `cli.py` | argumentos, variables de entorno, arranque y parada ordenada |
| `config.py` | `Config` (datos puros, sin globales) y valores por defecto |
| `settings.py` | los ajustes: esquema, validación, persistencia en `settings.json` y prioridad frente a flags y entorno |
| `settings_routes.py` | rutas HTTP de la pantalla de ajustes (leer, guardar, probar conexiones, modelos de Whisper) |
| `whisper_models.py` | catálogo de modelos de Whisper, los instalados y la descarga con verificación |
| `paths.py` | dónde guarda cada sistema los datos (`./data` en el código fuente; carpeta de usuario si está instalado) |
| `desktop.py` | punto de entrada de la aplicación instalada: sin consola, registro en fichero, instancia única |
| `app.py` | `App`: construye los servicios, lanza los hilos de fondo y arma `/api/channels` |
| `server.py` | `Handler` HTTP: rutas, protección de peticiones, estáticos y proxy |
| `net.py` | `Net`: lista de hosts permitidos, bloqueo de direcciones no públicas, redirecciones validadas |
| `store.py` | `Store`: canales, guías, estado de salud y canales propios, con un único `RLock` |
| `parser.py` | Markdown de TDTChannels ➜ canales (función pura) |
| `custom.py` | validación de los canales que pega el usuario |
| `hls.py` | reescritura de listas m3u8 para que todo vuelva al proxy (función pura) |
| `feeds.py` | descarga de las listas con ETag y reintentos |
| `epg.py` | XMLTV ➜ programas; *payloads* de la guía |
| `health.py` | sondeo de streams (lista ➜ variante ➜ segmento, o primeros bytes de audio) |
| `ai.py` | preselección de candidatos, petición al modelo y **validación** de su respuesta |
| `stt.py` | `Transcriber`, `Whisper` (cliente/lanzador), `PcmStream` y `Tap` |
| `logos.py` | caché de logos con detección de tipo por firma |
| `util.py` | normalización de texto |

Reglas de diseño:

- **Sin estado global.** Todo cuelga de un `App` que se construye con un `Config`; los tests montan
  cuantos quieran en paralelo.
- **Lógica pura aparte** (`parser`, `hls`, `epg.parse_xmltv`, `ai.sanitize_reply`, `stt.keep_segment`…)
  para probarla sin red ni hilos.
- **La red va por `Net`.** Lo único que descarga sin lista de hosts son las fuentes que el operador
  pasa por línea de comandos (`Net.fetch_trusted`).
- **Los hilos de fondo** (listas, guía, comprobación, transcripción) se paran con un `Event` en
  `App.close()`.

## Flujo del proxy

1. El navegador pide `/proxy?u=<url>&c=<canal propio>&s=<sesión>`.
2. `Net.open` comprueba el esquema, que el host esté permitido y que no resuelva a una dirección
   privada; en cada redirección repite la comprobación.
3. Si es una lista m3u8 se reescribe (`hls.rewrite_playlist`) y cada URI vuelve a apuntar al proxy,
   permitiendo su host. Si no, se reenvía por trozos.
4. Si la sesión `s` activó la transcripción, un `Tap` copia el segmento (o el audio continuo) a la
   cola del `Transcriber` sin retrasar la respuesta.
5. Las cabeceras de un canal propio (`c`) se añaden a la petición al origen y nunca llegan al navegador.

## Interfaz `tdtlocal/static/js/`

Módulos ES cargados con `<script type="module">`; no hace falta compilar nada. `hls.js` es un script
clásico que define `Hls` antes.

- `lib/` — funciones **puras** (texto, formato, EPG, filtros, órdenes del asistente, reparto del
  mosaico, plan de fuentes, alertas). Son las que prueban `tests/js/`.
- `state.js` — el estado compartido y las preferencias de `localStorage`.
- `tile.js` — una casilla: `<video>` + hls.js + cadena de fuentes de reserva + subtítulos. Recibe un
  *host* con lo que necesita de la aplicación, así que no conoce el estado global.
- `app.js` — controlador de la página (lista, panel, multivisión, subtítulos, datos y teclado).
- `guide.js`, `assistant.js`, `dialogs.js` — la guía, el asistente y los diálogos.
- `dom.js`, `store.js`, `api.js` — utilidades de DOM, de almacenamiento y de red.

## Ajustes

`Config` guarda los valores en vivo; `SettingsStore` los valida (`FIELDS` es la única lista de ajustes), los aplica y
los escribe en `data/settings.json`, solo los que difieren del valor por defecto. Los servicios leen `Config` cuando
la usan, así que un cambio vale al momento; los pocos que tienen estado (el `whisper-server` lanzado, los bucles de
fondo de listas y guía) reciben aviso en `App.apply_settings` según el `affects` de cada ajuste. Lo fijado por flag o
variable `TDT_<AJUSTE>` queda en `Config.locked`: la interfaz lo muestra bloqueado y nunca se guarda. Las rutas que
cambian algo solo aceptan peticiones del propio equipo.

La interfaz (`static/js/settings.js`) se genera a partir de `static/js/lib/settings-form.js`; una prueba comprueba que
coincide con `FIELDS`.

## Datos en `data/`

| Fichero | Contenido |
|---|---|
| `tv.json`, `radio.json` | última lista descargada y sus metadatos (ETag, fechas, error) |
| `status.json` | resultado de la última comprobación por URL |
| `custom.json` | canales propios, con sus cabeceras |
| `settings.json` | ajustes guardados (puede contener la clave de API: permisos 600 donde existen) |
| `logos/` | logos descargados (`.fail` = no reintentar durante 6 h) |

Las escrituras son atómicas (fichero temporal + `replace`).

## Pruebas

- `tests/helpers.py`: `FakeOrigin` (servidor HTTP programable en `127.0.0.1`), `AppCase` (aplicación
  sobre un directorio temporal) y `ServerCase` (con el servidor HTTP real en un puerto libre).
- Las pruebas de integración recorren el servidor de verdad: protección de peticiones, proxy con
  cabeceras de canal propio, estáticos, API, asistente (con un modelo simulado) y caché de logos.
- No se llama nunca a internet, ni a llama.cpp, ni a whisper.cpp, ni a ffmpeg.
