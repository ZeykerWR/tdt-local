#!/bin/sh
# Arranca TDT local y abre el navegador. Ajustes de esta máquina (rutas de whisper-server, etc.):
# iniciar.local.sh, que no se sube a git. Ejemplo:  export TDT_WHISPER_BIN=/ruta/a/whisper-server
cd "$(dirname "$0")" || exit 1
[ -f ./iniciar.local.sh ] && . ./iniciar.local.sh
exec python3 -m tdtlocal --open "$@"
