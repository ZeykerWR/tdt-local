#!/usr/bin/env python3
"""Rasterise the application icon (the same drawing as ``tdtlocal/static/icon.svg``) with the standard library.

Writes ``packaging/icons/``: ``icon-<size>.png``, ``icon.ico`` (Windows) and ``icon.icns`` (macOS). The outputs
are committed, so this only needs to run when the drawing changes::

    python packaging/make_icons.py
"""

from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path

OUT = Path(__file__).resolve().parent / "icons"
PNG_SIZES = (16, 32, 48, 64, 128, 256, 512, 1024)
ICO_SIZES = (16, 32, 48, 64, 128, 256)
# macOS icon types that hold PNG data -> pixel size
ICNS_TYPES = (("ic07", 128), ("ic08", 256), ("ic09", 512), ("ic10", 1024))

BG = (0x0D, 0x56, 0x62)
LIGHT = (0xE3, 0xF4, 0xF6)
SCREEN = (0x0B, 0x0D, 0x0C)
PLAY = (0x62, 0xC4, 0xD3)


def rounded_box(px: float, py: float, x0: float, y0: float, x1: float, y1: float, r: float) -> float:
    """Signed distance to a rounded rectangle: negative inside."""
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    qx = abs(px - cx) - ((x1 - x0) / 2 - r)
    qy = abs(py - cy) - ((y1 - y0) / 2 - r)
    return math.hypot(max(qx, 0), max(qy, 0)) + min(max(qx, qy), 0) - r


def segment_distance(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def in_triangle(px: float, py: float, a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> bool:
    def side(p: tuple[float, float], q: tuple[float, float]) -> float:
        return (px - q[0]) * (p[1] - q[1]) - (p[0] - q[0]) * (py - q[1])

    d1, d2, d3 = side(a, b), side(b, c), side(c, a)
    return not ((d1 < 0 or d2 < 0 or d3 < 0) and (d1 > 0 or d2 > 0 or d3 > 0))


def sample(x: float, y: float) -> tuple[int, int, int, int] | None:
    """Colour of the icon at a point of the 256x256 design space, or ``None`` if transparent."""
    if rounded_box(x, y, 0, 0, 256, 256, 48) > 0:
        return None
    colour = BG
    if min(segment_distance(x, y, 96, 30, 128, 64), segment_distance(x, y, 128, 64, 160, 30)) <= 6:
        colour = LIGHT
    d = rounded_box(x, y, 38, 62, 218, 190, 22)
    if d <= 5:
        colour = SCREEN if d < -5 else LIGHT
    if in_triangle(x, y, (110, 98), (110, 158), (162, 128)):
        colour = PLAY
    if rounded_box(x, y, 86, 206, 170, 218, 6) <= 0:
        colour = LIGHT
    return (*colour, 255)


def render(size: int) -> bytes:
    """RGBA bytes of the icon at ``size`` pixels, anti-aliased by supersampling."""
    ss = 4 if size <= 128 else 3 if size <= 256 else 2
    scale = 256 / size
    rows = bytearray()
    for j in range(size):
        rows.append(0)  # PNG filter type: none
        for i in range(size):
            r = g = b = a = 0
            for sj in range(ss):
                for si in range(ss):
                    c = sample((i + (si + 0.5) / ss) * scale, (j + (sj + 0.5) / ss) * scale)
                    if c:
                        r, g, b, a = r + c[0], g + c[1], b + c[2], a + 255
            n = ss * ss
            if a:
                covered = a // 255
                rows += bytes((r // covered, g // covered, b // covered, a // n))
            else:
                rows += b"\0\0\0\0"
    return bytes(rows)


def png(size: int) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(render(size), 9))
        + chunk(b"IEND", b"")
    )


def ico(images: dict[int, bytes]) -> bytes:
    """ICO container holding PNG images (supported since Windows Vista)."""
    entries, blobs, offset = b"", b"", 6 + 16 * len(images)
    for size, data in images.items():
        dim = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset + len(blobs))
        blobs += data
    return struct.pack("<HHH", 0, 1, len(images)) + entries + blobs


def icns(images: dict[int, bytes]) -> bytes:
    body = b"".join(
        kind.encode() + struct.pack(">I", 8 + len(images[size])) + images[size] for kind, size in ICNS_TYPES
    )
    return b"icns" + struct.pack(">I", 8 + len(body)) + body


def main() -> None:
    OUT.mkdir(exist_ok=True)
    images = {size: png(size) for size in PNG_SIZES}
    for size, data in images.items():
        (OUT / f"icon-{size}.png").write_bytes(data)
    (OUT / "icon.ico").write_bytes(ico({s: images[s] for s in ICO_SIZES}))
    (OUT / "icon.icns").write_bytes(icns(images))
    print("icons written to", OUT)


if __name__ == "__main__":
    main()
