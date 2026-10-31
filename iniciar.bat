@echo off
cd /d "%~dp0"
rem Ajustes de esta maquina (rutas de whisper-server, etc.): iniciar.local.bat, que no se sube a git.
rem Ejemplo:  set TDT_WHISPER_BIN=C:\ruta\a\whisper-server.exe
if exist "%~dp0iniciar.local.bat" call "%~dp0iniciar.local.bat"
where py >nul 2>&1
if %errorlevel%==0 (
  py -3 -m tdtlocal --open %*
  goto fin
)
where python >nul 2>&1
if %errorlevel%==0 (
  python -m tdtlocal --open %*
  goto fin
)
echo No se encuentra Python 3. Instalalo desde https://www.python.org/downloads/
:fin
pause
