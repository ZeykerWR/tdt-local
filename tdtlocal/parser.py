"""Parsing of the TDTChannels ``TELEVISION.md`` / ``RADIO.md`` Markdown tables."""

from __future__ import annotations

import logging
import re
from typing import Any

from .util import slugify

log = logging.getLogger(__name__)

Channel = dict[str, Any]

LINK = re.compile(r"\[([^\]]*)\]\((https?://[^)\s]+)\)")
UNFILLED_MACRO = re.compile(r"\[[A-Z_]+\]")


def fmt_of(label: str) -> str:
    """Stream format from a link label: ``"mp3 # 2"`` -> ``"mp3"``.

    In ``RADIO.md`` the link text names the format (aac, mp3, m3u8, stream).
    """
    match = re.match(r"[a-z0-9]+", label.strip().lower())
    return match.group(0) if match else ""


def _unique_id(base: str, group: str, category: str, used: set[str]) -> str:
    cid = base
    if cid in used:
        cid = f"{cid}-{slugify(group or category)}"
    candidate, n = cid, 2
    while candidate in used:
        candidate = f"{cid}-{n}"
        n += 1
    used.add(candidate)
    return candidate


def parse_markdown(text: str, kind: str = "tv") -> list[Channel]:
    """Parse the tables ``| Canal | M3U8 | Web | Logo | EPG ID | Info |`` under ``##`` / ``###`` headings.

    ``RADIO.md`` uses the same layout with ``Emisoras`` and ``Stream`` as headers. Rows with fewer
    cells than the header are skipped. Returns channel dicts ready to be stored as JSON.
    """
    channels: list[Channel] = []
    used: set[str] = set()
    category: str | None = None
    group: str | None = None
    columns: dict[str, int] | None = None
    skipped = 0

    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("### "):
            group = line[4:].strip()
            continue
        if line.startswith("## "):
            category, group = line[3:].strip(), None
            continue
        if not line.startswith("|") or category is None:
            continue

        cells = [c.strip() for c in line.strip("|").split("|")]
        if cells[0].lower() in ("canal", "emisoras"):
            columns = {c.lower(): i for i, c in enumerate(cells)}
            continue
        if columns is None or not cells[0] or set(cells[0]) <= set("-: "):
            continue
        if len(cells) < len(columns):
            skipped += 1
            continue

        def cell(name: str, cells: list[str] = cells, columns: dict[str, int] = columns) -> str:
            i = columns.get(name)
            return cells[i] if i is not None and i < len(cells) else ""

        name = cell("canal") or cell("emisoras")
        pairs: list[tuple[str, str]] = []
        for label, url in LINK.findall(cell("m3u8") or cell("stream")):
            if all(url != p[0] for p in pairs):
                pairs.append((url, fmt_of(label)))
        # URLs with unfilled macros ([IP], [UA]...) are only usable by ad servers: keep them last
        pairs.sort(key=lambda p: 1 if UNFILLED_MACRO.search(p[0]) else 0)

        epg = cell("epg id")
        channels.append(
            {
                "id": _unique_id(("radio-" if kind == "radio" else "") + slugify(name), group or "", category, used),
                "name": name,
                "kind": kind,
                "category": category,
                "group": group or "",
                "sources": [p[0] for p in pairs],
                "fmts": [p[1] for p in pairs],
                "web": next((u for _, u in LINK.findall(cell("web"))), ""),
                "logo": next((u for _, u in LINK.findall(cell("logo"))), ""),
                "epg": "" if epg == "-" else epg,
                "tags": [t.strip() for t in cell("info").split(",") if t.strip() and t.strip() != "-"],
            }
        )
    if skipped:
        log.warning("aviso: %d filas con menos columnas de las esperadas, omitidas", skipped)
    return channels
