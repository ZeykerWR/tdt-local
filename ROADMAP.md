# Hoja de ruta

Ideas ordenadas aproximadamente por valor. Lo marcado con ✅ ya está hecho. Las propuestas nuevas son
bienvenidas como *issues*.

## Reproducción
- [ ] **Canales de YouTube (vídeos, no directos):** añadir un canal por `@usuario`; sus últimos vídeos salen del RSS
  público (`youtube.com/feeds/videos.xml?channel_id=…`) y se reproducen con el reproductor incrustado. Sin
  subtítulos de Whisper (el audio no pasa por el proxy).
- [ ] Selector de resolución (niveles de hls.js), audio alternativo y subtítulos del propio stream.
- [ ] Indicador de *buffering*, panel de estadísticas y botón «volver al directo».
- [ ] Forzar IPv4 por canal propio (algunas CDN cortan IPv6).
- [ ] Metadatos ICY («está sonando…») de las emisoras que los emiten.
- [ ] Arrastrar un canal de la lista a una casilla concreta del mosaico.

## Guía de programación
- [ ] Unos 33 IDs de tele y unos 210 de radio de las listas no están en el XMLTV (locales, `OC_*` de Onda
  Cero…): otra fuente o una tabla de equivalencias.
- [ ] Recordatorios: avisar cuando empiece un programa marcado (notificación del navegador).
- [ ] Buscar en la guía («qué ponen esta noche de…») a través de todos los canales.
- [ ] Refrescar la guía abierta cuando acaba el programa en curso.

## IA local
- [ ] **Contexto online:** de lo que se dice (transcripción o guía) sacar 1–3 consultas con el modelo y listar
  titulares de medios (RSS de noticias), agrupados por medio.
- [ ] **Rotación inteligente:** priorizar la casilla cuyo programa o transcripción encaja con temas del usuario.
- [ ] **«Qué ver hoy»:** agenda con favoritos e historial local.
- [ ] Emparejar con IA los canales sin EPG con los del XMLTV (script puntual).
- [ ] Transcripción: solapar 1–2 s entre segmentos, soportar fMP4/CMAF (guardar el segmento `EXT-X-MAP`) y VAD.
- [ ] Transcripción de radio continua: retrasar el audio unos segundos para que los subtítulos salgan sincronizados.
- [ ] Parar `whisper-server` aunque el servidor muera a la fuerza (objeto *Job* de Windows).

## Cuenta y preferencias
- [ ] Descargar también el programa `whisper-server` (binarios de whisper.cpp) desde Ajustes.
- [ ] Elegir el mensaje del sistema del asistente y exportar/importar los ajustes.
- [ ] Favoritos y preferencias en el servidor (`data/prefs.json`): hoy están en `localStorage`, que va por
  origen y se pierde al cambiar de puerto o usar `--lan`.
- [ ] Reordenar favoritos y numeración propia (hoy el número es la posición en la vista filtrada).
- [ ] PWA para tablet y móvil (`manifest.json` e icono).

## Robustez y seguridad
- [ ] Limitar la lista de hosts permitidos por canal (hoy crece con cada redirección o segmento validado).
- [ ] Cerrar la ventana de DNS rebinding en `Net.check_url` (conectar a la IP ya validada).
- [ ] Autenticación opcional para `--lan` (`--token`).
- [ ] Historial de salud: guardar los últimos N resultados por fuente y priorizar la más estable.
- [ ] Caché corto (~30 s) de segmentos en el proxy para varios clientes en la LAN.
- [ ] Limpiar la caché de logos (`data/logos/`): borrar los de canales que ya no están y caducar los `.fail`.
- [ ] Mostrar o descartar las URL con macros sin rellenar (`[IP]`, `[UA]`).

## Distribución
- [ ] Firmar los instaladores (Authenticode en Windows; Developer ID y notarización en macOS).
- [ ] winget, Homebrew cask y un repositorio APT / Flatpak.
- [ ] Instalador de Windows para ARM y paquete `.rpm`.
- [ ] Icono en la bandeja del sistema en lugar del botón «Salir».

## Calidad
- [ ] Comprobación de tipos con `mypy` en la CI (las anotaciones ya están; falta ejecutarlo y arreglar lo que salga).
- [ ] Medir la cobertura de las pruebas y subir la de `stt.py` (hilos y procesos).
- [ ] Pruebas de interfaz con un navegador sin cabeza.
- [x] Pruebas de Python y del navegador, lint y CI.
- [x] Paquete instalable sin estado global.
