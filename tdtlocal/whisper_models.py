"""Whisper speech-recognition models: what is installed, a catalogue to download from, and the download itself.

Only models of this catalogue can be fetched, always from the whisper.cpp repository on Hugging Face: the
interface never sends a URL, just the name of a catalogue entry.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import shutil
import threading
import urllib.error
from pathlib import Path
from typing import Any

from .config import Config
from .net import Net

log = logging.getLogger(__name__)

REPO = "ggerganov/whisper.cpp"
BASE_URL = f"https://huggingface.co/{REPO}/resolve/main/"
TREE_URL = f"https://huggingface.co/api/models/{REPO}/tree/main"
CHUNK = 1 << 20
DISK_MARGIN = 200 * 1024 * 1024
LABELS = {"fast": "rápido", "balanced": "equilibrado", "accurate": "preciso"}

# (name, file, approximate size in MB, speed/quality, note)
CATALOG: tuple[dict[str, Any], ...] = (
    {"name": "tiny-q5_1", "mb": 31, "level": "fast", "note": "Mínimo: solo para probar"},
    {"name": "base-q5_1", "mb": 57, "level": "fast", "note": "Muy ligero; falla con ruido y acentos"},
    {"name": "small-q5_1", "mb": 181, "level": "balanced", "note": "Buen equilibrio en CPU"},
    {"name": "medium-q5_0", "mb": 539, "level": "balanced", "note": "Más preciso; pide más CPU o GPU"},
    {"name": "large-v3-turbo-q5_0", "mb": 574, "level": "accurate", "note": "Recomendado con GPU: casi como large-v3"},
    {"name": "large-v3-q5_0", "mb": 1100, "level": "accurate", "note": "El más preciso; lento sin GPU"},
    {"name": "tiny", "mb": 75, "level": "fast", "note": "Sin cuantizar"},
    {"name": "base", "mb": 142, "level": "fast", "note": "Sin cuantizar"},
    {"name": "small", "mb": 466, "level": "balanced", "note": "Sin cuantizar"},
    {"name": "medium", "mb": 1500, "level": "balanced", "note": "Sin cuantizar"},
    {"name": "large-v3-turbo", "mb": 1600, "level": "accurate", "note": "Sin cuantizar"},
    {"name": "large-v3", "mb": 2900, "level": "accurate", "note": "Sin cuantizar"},
)
for _entry in CATALOG:
    _entry["file"] = f"ggml-{_entry['name']}.bin"
BY_NAME = {e["name"]: e for e in CATALOG}


def installed_models(models_dir: Path) -> list[dict[str, Any]]:
    """The ``ggml-*.bin`` files in ``models_dir``, smallest first."""
    if not models_dir.is_dir():
        return []
    found = [{"file": p.name, "path": str(p), "bytes": p.stat().st_size} for p in models_dir.glob("ggml-*.bin")]
    return sorted(found, key=lambda m: (m["bytes"], m["file"]))


def catalogue(models_dir: Path) -> list[dict[str, Any]]:
    """The catalogue with an ``installed`` flag, for the interface."""
    have = {m["file"] for m in installed_models(models_dir)}
    return [{**e, "installed": e["file"] in have, "label": LABELS[e["level"]]} for e in CATALOG]


class ModelDownloader:
    """One download at a time, in a background thread, with progress, cancellation and integrity check."""

    def __init__(self, config: Config, net: Net) -> None:
        self.config = config
        self.net = net
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None
        self._status: dict[str, Any] = {"state": "idle"}

    def status(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._status)

    def _set(self, **fields: Any) -> None:
        with self._lock:
            self._status.update(fields)

    def start(self, name: str) -> bool:
        """Begin downloading a catalogue model. ``False`` if another download is running."""
        entry = BY_NAME.get(name)
        if entry is None:
            raise ValueError("modelo desconocido")
        with self._lock:
            if self._status.get("state") == "running":
                return False
            self._cancel.clear()
            self._status = {"state": "running", "name": name, "file": entry["file"], "done": 0, "total": 0, "error": ""}
        self._thread = threading.Thread(target=self._run, args=(entry,), daemon=True, name="model-download")
        self._thread.start()
        return True

    def cancel(self) -> None:
        self._cancel.set()

    def wait(self, timeout: float | None = None) -> None:
        """Block until the running download ends (used by tests)."""
        if self._thread:
            self._thread.join(timeout)

    def _expected(self, file: str) -> tuple[str | None, int | None]:
        """``(sha256, size)`` the repository publishes for ``file``, or ``(None, None)`` if it cannot be read."""
        try:
            body, _ = self.net.fetch_trusted(TREE_URL, timeout=20, limit=2_000_000)
            for item in json.loads(body.decode("utf-8", "replace")):
                if item.get("path") == file:
                    lfs = item.get("lfs") or {}
                    return lfs.get("oid"), lfs.get("size") or item.get("size")
        except (OSError, ValueError, AttributeError, TypeError):
            log.info("no se pudo leer la huella publicada de %s: no se verificará", file)
        return None, None

    def _run(self, entry: dict[str, Any]) -> None:
        models_dir = Path(self.config.models_dir)
        final = models_dir / entry["file"]
        part = final.with_suffix(".bin.part")
        try:
            models_dir.mkdir(parents=True, exist_ok=True)
            sha, size = self._expected(entry["file"])
            digest = hashlib.sha256()
            with self.net.stream_trusted(BASE_URL + entry["file"], timeout=30) as response:
                total = int(response.headers.get("Content-Length") or size or 0)
                if total and shutil.disk_usage(models_dir).free < total + DISK_MARGIN:
                    raise OSError("no hay espacio en disco suficiente para el modelo")
                self._set(total=total)
                done = 0
                with part.open("wb") as out:
                    while True:
                        if self._cancel.is_set():
                            raise InterruptedError
                        block = response.read(CHUNK)
                        if not block:
                            break
                        out.write(block)
                        digest.update(block)
                        done += len(block)
                        self._set(done=done)
            if total and done != total:
                raise OSError(f"descarga incompleta ({done} de {total} bytes)")
            if sha and digest.hexdigest() != sha:
                raise OSError("la huella SHA-256 no coincide con la publicada: archivo descartado")
            part.replace(final)
            self._set(state="done", verified=bool(sha), done=final.stat().st_size, path=str(final))
            log.info("modelo descargado: %s", final.name)
        except InterruptedError:
            self._set(state="cancelled", error="")
        except (OSError, urllib.error.URLError) as exc:
            log.warning("descarga del modelo %s: %s", entry["file"], exc)
            self._set(state="error", error=str(exc) or type(exc).__name__)
        finally:
            with contextlib.suppress(OSError):
                part.unlink()
