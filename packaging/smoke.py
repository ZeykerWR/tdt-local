#!/usr/bin/env python3
"""Smoke test of the packaged desktop app, checked from outside (the packaged app has no debug port).

    python packaging/smoke.py "dist/electron/TDT local-win32-x64"

It starts the app with an empty data folder and checks that: it opens its server on the port it records, the server
answers and serves the page, a second launch hands over to the first one and exits, and quitting stops the app and frees
the port. On Linux run it under ``xvfb-run -a`` when there is no display. Exit code 0 when everything holds.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

START_TIMEOUT = 120  # the first start unpacks and loads the page: be generous on a cold CI runner
QUIT_TIMEOUT = 30


def executable(app_dir: Path) -> Path:
    """The program inside the packaged folder (``tdt-local``, ``tdt-local.exe`` or the one in the macOS bundle)."""
    if sys.platform == "darwin":
        macos = next(app_dir.glob("*.app")) / "Contents" / "MacOS"
        return next(p for p in sorted(macos.iterdir()) if p.is_file() and os.access(p, os.X_OK))
    return app_dir / ("tdt-local.exe" if sys.platform == "win32" else "tdt-local")


def get(url: str, timeout: float = 5) -> bytes:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(url, timeout=timeout) as response:
        return response.read()


def wait_until(check, timeout: float, what: str):
    limit = time.time() + timeout
    while time.time() < limit:
        try:
            value = check()
        except (OSError, ValueError):
            value = None
        if value:
            return value
        time.sleep(0.5)
    raise SystemExit(f"FALLO: {what} (tras {timeout:g} s)")


def port_open(port: int) -> bool:
    with socket.socket() as probe:
        return probe.connect_ex(("127.0.0.1", port)) == 0


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 2
    exe = executable(Path(argv[0]))
    extra = os.environ.get("TDT_SMOKE_ARGS", "").split()  # e.g. --no-sandbox where the system forbids the sandbox
    with tempfile.TemporaryDirectory() as data:
        env = dict(os.environ, TDT_DATA_DIR=data)
        log_file = Path(data) / "desktop" / "logs" / "tdt-local.log"
        port_file = Path(data) / "desktop" / "port.json"
        app = subprocess.Popen([str(exe), *extra], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            port = wait_until(
                lambda: json.loads(port_file.read_text())["port"], START_TIMEOUT, "la app no abrió su servidor"
            )
            answer = wait_until(
                lambda: json.loads(get(f"http://127.0.0.1:{port}/api/version")), 30, "el servidor no responde"
            )
            assert answer.get("name") == "tdt-local", answer
            print(f"servidor en el puerto {port}, versión {answer.get('version')}")
            page = get(f"http://127.0.0.1:{port}/").decode("utf-8", "replace")
            assert "<title>" in page and len(get(f"http://127.0.0.1:{port}/js/app.js")) > 1000, "la página no se sirve"
            print("la página y sus módulos se sirven")
            log = wait_until(
                lambda: log_file.read_text("utf-8") if "servidor listo" in log_file.read_text("utf-8") else "",
                30,
                "no hay «servidor listo» en el registro",
            )
            print([line for line in log.splitlines() if "[plugins]" in line] or "(sin línea de plugins)")

            second = subprocess.Popen([str(exe), *extra], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            wait_until(lambda: second.poll() is not None, 30, "un segundo lanzamiento no cedió el paso")
            assert app.poll() is None, "la primera instancia se cerró con el segundo lanzamiento"
            print("un segundo lanzamiento le cede el paso al primero")

            request = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/quit",
                data=b"{}",
                headers={"content-type": "application/json"},
                method="POST",
            )
            urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=5).read()
            wait_until(lambda: app.poll() is not None, QUIT_TIMEOUT, "la app no se cerró al salir")
            wait_until(lambda: not port_open(port), 10, "el puerto sigue abierto tras salir")
            print("al salir, la app se cierra y el puerto queda libre")
        except (AssertionError, SystemExit) as error:
            print(f"{error}", file=sys.stderr)
            if log_file.exists():
                print("--- registro de la app ---\n" + log_file.read_text("utf-8"), file=sys.stderr)
            return 1
        finally:
            if app.poll() is None:
                app.kill()
    print("todo correcto")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
