"""PyInstaller entry point: the server alone, started by the Electron app (it opens no browser and has no window)."""

import sys

from tdtlocal.cli import main

if __name__ == "__main__":
    # The app reads what the server prints as UTF-8, but a frozen program ignores PYTHONUTF8 and would write in the
    # console's code page (accents arrived as «�» in the Registro).
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    main()
