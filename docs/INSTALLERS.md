# Instaladores

TDT local se distribuye como aplicación de escritorio para Windows, macOS y Linux. Cada instalador
incluye su propio Python: **no hace falta tener nada instalado** para usarlo. Se crean con
[PyInstaller](https://pyinstaller.org) desde `packaging/build.py`, y la CI los publica en cada
*release* (`.github/workflows/release.yml`).

| Sistema | Archivo | Cómo se instala |
|---|---|---|
| Windows 10/11 (x64) | `tdt-local-<versión>-windows-x64-setup.exe` | doble clic; por defecto en tu usuario, sin administrador |
| Windows | `tdt-local-<versión>-windows-x64-portable.zip` | descomprimir y ejecutar `tdt-local.exe` |
| macOS 11+ (Intel) | `tdt-local-<versión>-macos-x64.dmg` | arrastrar **TDT local** a Aplicaciones |
| macOS 11+ (Apple Silicon) | `tdt-local-<versión>-macos-arm64.dmg` | ídem |
| Debian / Ubuntu | `tdt-local_<versión>_amd64.deb` | `sudo apt install ./tdt-local_<versión>_amd64.deb` |
| Cualquier Linux | `tdt-local-<versión>-linux-x64.tar.gz` | descomprimir y `./install.sh` (en tu usuario, sin root) |

`SHA256SUMS.txt` lleva las huellas de todos los archivos.

## Cómo se comporta la aplicación instalada

- Al abrirla arranca el servidor **sin ventana de consola** y abre el navegador en
  `http://127.0.0.1:8788/`. Si ya estaba en marcha, solo abre esa instancia; si el puerto está
  ocupado por otro programa, usa otro libre.
- Para cerrarla, el botón **Salir** (abajo en el panel de canales). Sin él, el servidor seguiría
  en segundo plano.
- Guarda sus datos por usuario, no en la carpeta de instalación:

  | Sistema | Datos |
  |---|---|
  | Windows | `%LOCALAPPDATA%\TDT local\` |
  | macOS | `~/Library/Application Support/TDT local/` |
  | Linux | `~/.local/share/tdt-local/` (o `$XDG_DATA_HOME/tdt-local/`) |

  Ahí están las listas, los canales propios, la caché de logos, el registro (`tdt-local.log`) y la
  carpeta `models/` para el modelo de Whisper. `TDT_DATA_DIR` las cambia de sitio.
- Whisper y el asistente de IA son opcionales y **no se incluyen**. Se configuran desde **Ajustes** (el botón del panel
  de canales), que guarda todo en `settings.json` dentro de esa carpeta y permite descargar los modelos de Whisper;
  no hace falta tocar variables de entorno. Si defines alguna `TDT_*`, manda sobre lo guardado.
- Desinstalar: el desinstalador de Windows (pregunta si quieres borrar los datos), arrastrar la
  aplicación a la papelera en macOS, `sudo apt remove tdt-local` o `./uninstall.sh` en Linux.

## Qué verá el usuario al instalar (los paquetes no están firmados)

- **Windows:** SmartScreen avisa de «editor desconocido»: *Más información ➜ Ejecutar de todas formas*.
- **macOS:** Gatekeeper no abre apps sin notarizar con doble clic. La primera vez: clic derecho sobre
  la app ➜ **Abrir** ➜ **Abrir**; o en *Ajustes del Sistema ➜ Privacidad y seguridad ➜ Abrir igualmente*.
  La app lleva una firma *ad hoc* (necesaria en Apple Silicon), que no sustituye a una notarización.
- **Linux:** sin avisos. Los `.deb` necesitan glibc 2.31 o superior (Ubuntu 20.04+, Debian 11+).

Firmar quita esos avisos, pero requiere certificados de pago (Authenticode para Windows; Apple
Developer ID y notarización para macOS). Cuando existan, se añaden como secretos del repositorio y
pasos de `release.yml` (`signtool`, `codesign --options runtime`, `notarytool`).

## Construir en local

Hace falta compilar en cada sistema para ese sistema (PyInstaller no hace compilación cruzada).

```
python -m pip install pyinstaller certifi
python packaging/build.py
```

Requisitos extra: en Windows, [Inno Setup 6](https://jrsoftware.org/isinfo.php) (`ISCC.exe`); en
macOS, las herramientas de línea de comandos de Xcode (`codesign`, `hdiutil`); en Linux, `dpkg-deb`
para el `.deb` (el `.tar.gz` se genera siempre). El resultado queda en `dist/installers/`.
`TDT_HOMEPAGE` cambia la dirección del proyecto que lleva el `.deb` (por defecto, este repositorio).

## Publicar una versión

1. Sube `__version__` en `tdtlocal/__init__.py` y anota los cambios en `CHANGELOG.md`.
2. `git tag v1.2.3 && git push --tags`.
3. La CI comprueba que el tag coincide con la versión, pasa las pruebas, construye los cuatro
   instaladores y crea el *release* con ellos y con `SHA256SUMS.txt`.

## Licencias dentro de los instaladores

Cada instalador lleva `LICENSE` (Apache 2.0), `NOTICE` (la cita de TDTChannels, hls.js y el resto) y
`licenses/PYTHON-LICENSE.txt` (licencia del intérprete de Python que se redistribuye). La propia
aplicación muestra los créditos en **Créditos y licencias** (`/about.html`). PyInstaller es GPL-2.0
con una excepción que permite distribuir los programas generados con cualquier licencia.

## Lo que no se ha podido comprobar desde el entorno de desarrollo

Las pruebas automáticas cubren el nombre de los paquetes, los ficheros de control, los iconos, la
ruta de datos de cada sistema, el punto de entrada de escritorio y la validación de certificados.
El empaquetado de macOS y Linux y el instalador de Windows solo se ejecutan de verdad en la CI de
`release.yml`: la primera ejecución puede necesitar ajustes (por ejemplo, las etiquetas de los
*runners* de macOS).
