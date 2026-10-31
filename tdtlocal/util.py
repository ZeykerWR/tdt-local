"""Small text helpers shared by several modules."""

from __future__ import annotations

import re
import unicodedata


def strip_accents(text: str) -> str:
    """Remove combining marks: ``"canción"`` -> ``"cancion"``."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def normalize(text: str) -> str:
    """Lower-case and accent-free form used to compare user text with channel names."""
    return strip_accents(text).lower()


def slugify(text: str) -> str:
    """URL-friendly identifier; never empty (falls back to ``"canal"``)."""
    return re.sub(r"[^a-z0-9]+", "-", normalize(text)).strip("-") or "canal"
