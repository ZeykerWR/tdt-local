"""Disk cache for channel logos, fetched through the guarded network layer."""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

from .net import Net
from .store import Store

MAX_LOGO_BYTES = 1_000_000
FAILURE_TTL = 6 * 3600  # do not retry a broken logo URL for this long

_MAGIC = [
    (b"\x89PNG\r\n\x1a\n", "image/png", ".png"),
    (b"\xff\xd8\xff", "image/jpeg", ".jpg"),
    (b"GIF8", "image/gif", ".gif"),
]
EXT_TYPE = {".png": "image/png", ".jpg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp"}


def sniff_image(data: bytes) -> tuple[str, str] | None:
    """``(content_type, extension)`` from the file signature, or ``None`` if it is not an accepted image."""
    for magic, ctype, ext in _MAGIC:
        if data.startswith(magic):
            return ctype, ext
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", ".webp"
    return None


class LogoCache:
    def __init__(self, store: Store, net: Net, directory: Path) -> None:
        self.store = store
        self.net = net
        self.directory = directory

    def get(self, url: str) -> tuple[str, bytes] | None:
        """``(content_type, bytes)`` for a logo URL taken from the lists, or ``None`` if unknown/unavailable."""
        if url not in self.store.logo_urls:
            return None
        key = hashlib.sha1(url.encode(), usedforsecurity=False).hexdigest()
        self.directory.mkdir(parents=True, exist_ok=True)
        hit = next((p for p in self.directory.glob(key + ".*") if p.suffix in EXT_TYPE), None)
        if hit is None:
            failure = self.directory / (key + ".fail")
            if failure.exists() and time.time() - failure.stat().st_mtime < FAILURE_TTL:
                return None
            try:
                with self.net.open(url, {"Accept": "image/*"}, False, 10) as response:
                    body = response.read(MAX_LOGO_BYTES + 1)
                kind = sniff_image(body) if len(body) <= MAX_LOGO_BYTES else None
                if not kind:
                    raise ValueError("no es una imagen admitida")
                hit = self.directory / (key + kind[1])
                hit.write_bytes(body)
            except Exception:
                failure.write_bytes(b"")
                return None
        return EXT_TYPE[hit.suffix], hit.read_bytes()
