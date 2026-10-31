"""Entry point of the installed desktop app (Start menu / Launchpad / application launcher).

Unlike the command line it has no console: it logs to a file in the user's data directory, opens the browser,
offers a "Salir" button to stop the server, and if TDT local is already running it just shows that instance.
"""

from __future__ import annotations

import json
import logging
import socket
import urllib.request
import webbrowser
from pathlib import Path

from .cli import configure_logging, run
from .config import Config

log = logging.getLogger("tdtlocal")


def running_instance(port: int, host: str = "127.0.0.1") -> bool:
    """True if a TDT local server already answers on ``host:port``."""
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f"http://{host}:{port}/api/version", timeout=2) as response:
            return json.loads(response.read(1000)).get("name") == "tdt-local"
    except (OSError, ValueError, AttributeError):
        return False


def port_is_free(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket() as probe:
        return probe.connect_ex((host, port)) != 0


def main() -> None:
    config = Config(allow_quit=True)
    log_file = Path(config.data_dir) / "tdt-local.log"
    configure_logging(config, log_file)
    if running_instance(config.port):
        log.info("TDT local ya está en marcha: se abre esa instancia")
        webbrowser.open(f"http://127.0.0.1:{config.port}/")
        return
    if not port_is_free(config.port):  # another program owns it: let the system choose a port
        log.warning("el puerto %d está ocupado; se usa otro", config.port)
        config.port = 0
    run(config, open_browser=True)


if __name__ == "__main__":
    main()
