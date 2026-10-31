"""Programme guide (EPG): XMLTV download, parsing and the "now / next" views served to the browser."""

from __future__ import annotations

import calendar
import gzip
import io
import logging
import re
import threading
import time
import urllib.error
import xml.etree.ElementTree as ET
from typing import Any

from .config import Config
from .net import Net
from .store import Programme, Store

log = logging.getLogger(__name__)

EPG_INTERVAL = 3600  # the source is regenerated hourly; with an ETag we only download when it changes
EPG_RETRY = 600
TICK_SECONDS = 30  # how often the background loop re-reads the settings
MAX_GZ = 12_000_000
MAX_XML = 60_000_000
DESCRIPTION_LIMIT = 600
XMLTV_TS = re.compile(r"(\d{14})(?:\s*(Z|[+-]\d{4}))?")


def xmltv_ts(value: str | None) -> int:
    """``"20261030065000 +0100"`` -> epoch seconds (UTC). Raises :class:`ValueError` if malformed."""
    match = XMLTV_TS.match(value or "")
    if not match:
        raise ValueError("fecha XMLTV no válida")
    ts = calendar.timegm(time.strptime(match.group(1), "%Y%m%d%H%M%S"))
    zone = match.group(2)
    if zone and zone != "Z":
        sign = 1 if zone[0] == "+" else -1
        ts -= sign * (int(zone[1:3]) * 3600 + int(zone[3:5]) * 60)
    return ts


def parse_xmltv(data: bytes, now: float | None = None) -> dict[str, list[Programme]]:
    """``{epg_id: [[start, end, title, description, category], ...]}`` without programmes already over.

    Documents declaring entities are rejected (billion-laughs protection).
    """
    if b"<!entity" in data.lower():
        raise ValueError("XML con entidades: rechazado")
    now = time.time() if now is None else now
    root = ET.fromstring(data)  # noqa: S314 - entities rejected above, size capped by the caller
    out: dict[str, list[Programme]] = {}
    for programme in root.iter("programme"):
        channel = programme.get("channel")
        try:
            start, end = xmltv_ts(programme.get("start")), xmltv_ts(programme.get("stop"))
        except ValueError:
            continue
        title = (programme.findtext("title") or "").strip()
        if not channel or not title or end <= start or end <= now:
            continue
        category = (programme.findtext("category") or "").strip()
        out.setdefault(channel, []).append(
            [
                start,
                end,
                title,
                (programme.findtext("desc") or "").strip()[:DESCRIPTION_LIMIT],
                "" if category == "Desconocido" else category,
            ]
        )
    for items in out.values():
        items.sort(key=lambda p: p[0])
    return out


class EpgSyncer:
    """Keeps ``store.epg`` fresh and builds the JSON the browser asks for."""

    def __init__(self, config: Config, store: Store, net: Net) -> None:
        self.config = config
        self.store = store
        self.net = net
        self._lock = threading.Lock()
        self._next_due = 0.0

    def _fetch(self, kind: str, force: bool) -> tuple[dict[str, list[Programme]], str | None] | None:
        """``(guide, etag)``, or ``None`` when the source did not change."""
        store = self.store
        headers = {}
        etag = store.epg_meta["etag"].get(kind)
        if etag and store.epg[kind] and not force:
            headers["If-None-Match"] = etag
        try:
            body, response_headers = self.net.fetch_trusted(self.config.epg_sources[kind], headers, limit=MAX_GZ)
        except urllib.error.HTTPError as exc:
            if exc.code == 304:
                return None
            raise
        if len(body) > MAX_GZ:
            raise ValueError("la guía es demasiado grande")
        if body[:2] == b"\x1f\x8b":
            body = gzip.GzipFile(fileobj=io.BytesIO(body)).read(MAX_XML + 1)
        if len(body) > MAX_XML:
            raise ValueError("la guía descomprimida es demasiado grande")
        return parse_xmltv(body), response_headers.get("ETag")

    def sync(self, force: bool = False) -> dict[str, Any]:
        """Download the TV and radio guides. A failure in one does not discard the other."""
        with self._lock:
            store = self.store
            now = int(time.time())
            errors: list[str] = []
            changed = False
            for kind in ("tv", "radio"):
                try:
                    fetched = self._fetch(kind, force)
                except Exception as exc:
                    if isinstance(exc, urllib.error.HTTPError):
                        errors.append(f"{kind}: HTTP {exc.code}")
                    else:
                        errors.append(f"{kind}: {type(exc).__name__} {exc}")
                    continue
                if fetched is None:
                    continue
                with store.lock:
                    store.epg[kind] = fetched[0]
                    store.epg_meta["etag"][kind] = fetched[1]
                changed = True
            with store.lock:
                store.epg_meta.update(checked=now, error="; ".join(errors) or None)
                if changed:
                    store.epg_meta["updated"] = now
                channels = sum(len(v) for v in store.epg.values())
            return {"changed": changed, "channels": channels, "error": errors or None}

    def refresh_soon(self) -> None:
        """Ask the background loop to download the guides at its next tick (enabled, or sources changed)."""
        self._next_due = 0.0

    def run(self, stop: threading.Event) -> None:
        """Background loop. Runs even when the guide is disabled, so enabling it later needs no restart."""
        while True:
            if self.config.epg_enabled and time.time() >= self._next_due:
                result = self.sync(force=self._next_due == 0.0)
                if result["error"]:
                    log.warning("guía de programación: %s", "; ".join(result["error"]))
                    self._next_due = time.time() + EPG_RETRY
                else:
                    if result["changed"]:
                        log.info("guía de programación: %d canales", result["channels"])
                    self._next_due = time.time() + EPG_INTERVAL
            if stop.wait(TICK_SECONDS):
                return

    def payload(self, epg_id: str = "", now: float | None = None) -> dict[str, Any]:
        """Without an id: the next three programmes of every channel. With an id: that channel's full guide."""
        now = time.time() if now is None else now
        store = self.store
        with store.lock:
            if epg_id:
                items = store.epg["tv"].get(epg_id) or store.epg["radio"].get(epg_id) or []
                return {"id": epg_id, "programmes": [p for p in items if p[1] > now][:40]}
            upcoming: dict[str, list[Programme]] = {}
            for kind in ("tv", "radio"):
                for key, programmes in store.epg[kind].items():
                    head = [p[:3] for p in programmes if p[1] > now][:3]
                    if head:
                        upcoming[key] = head
            return {
                "updated": store.epg_meta["updated"],
                "checked": store.epg_meta["checked"],
                "error": store.epg_meta["error"],
                "now": upcoming,
            }
