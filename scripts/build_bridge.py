#!/usr/bin/env python3
"""Build ``tools/puente-atresplayer/audio-chain.js``: the sound chain of the page, as a script the extension can load.

The leveler and the equalizer live in ``tdtlocal/static/js/lib/audio.js`` (settings and maths) and ``audio.js``
(the Web Audio chain). A content script of an extension cannot import modules, so this joins the two into one classic
script that publishes ``globalThis.TDT_AUDIO``. The result is committed; ``--check`` fails if it is out of date, and
so does a test.

    python scripts/build_bridge.py          # write it
    python scripts/build_bridge.py --check  # only compare
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JS = ROOT / "tdtlocal" / "static" / "js"
OUT = ROOT / "tools" / "puente-atresplayer" / "audio-chain.js"
EXPORTS = ("chainFor", "wake", "awake", "audioSupported", "sanitize")

HEADER = """// GENERADO por scripts/build_bridge.py a partir de tdtlocal/static/js/lib/audio.js y
// tdtlocal/static/js/audio.js.
// No lo edites: cambia esos archivos y vuelve a ejecutar el script. Es la cadena de sonido de TDT local (igualador
// de volumen y ecualizador) empaquetada como un script normal, para que la extensión del puente la use dentro del
// reproductor.
"""


def _plain(source: str) -> str:
    """The module as plain script code: no ``import`` and no ``export``."""
    source = re.sub(r"^import \{[^}]*\} from '[^']+';\n", "", source, flags=re.MULTILINE)
    return re.sub(r"^export (async function|function|const|class|let) ", r"\1 ", source, flags=re.MULTILINE)


def build() -> str:
    parts = [
        _plain((JS / "lib" / "audio.js").read_text(encoding="utf-8")),
        _plain((JS / "audio.js").read_text(encoding="utf-8")),
    ]
    body = "\n".join(parts)
    published = ", ".join(EXPORTS)
    return f"{HEADER}(function () {{\n'use strict';\n{body}\nglobalThis.TDT_AUDIO = {{ {published} }};\n}}());\n"


def main(argv: list[str]) -> int:
    text = build()
    if "--check" in argv:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != text:
            print(f"{OUT.relative_to(ROOT)} no está al día: ejecuta python scripts/build_bridge.py")
            return 1
        return 0
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"escrito {OUT.relative_to(ROOT)} ({len(text)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
