"""Live transcription: ffmpeg turns the audio into PCM and whisper.cpp's ``whisper-server`` transcribes it.

The audio never leaves the machine. HLS segments passing through the proxy are copied to a queue
(:class:`Tap`), decoded, transcribed by a single worker thread and handed to the browser, which polls
them by session tag.
"""

from __future__ import annotations

import array
import collections
import contextlib
import json
import logging
import os
import queue
import re
import shutil
import struct
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from .config import Config
from .net import LOCAL_OPENER
from .util import normalize

log = logging.getLogger(__name__)

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
SAMPLE_RATE = 16000
BYTES_PER_SECOND = SAMPLE_RATE * 2  # 16-bit mono
WINDOW_SECONDS = 6.0  # audio per request for continuous streams (in HLS: one segment)
SESSION_TTL = 300  # sessions the browser stopped polling are dropped
MAX_SEGMENT_BYTES = 16_000_000
QUEUE_SIZE = 24
AVAILABILITY_TTL = 30  # seconds to remember whether Whisper is usable
MIN_SECONDS = 0.5
MIN_RMS = 120  # quieter than this is silence: not worth sending to the model

HALLUCINATIONS = (
    "subtitulos realizados por",
    "subtitulado por",
    "amara.org",
    "gracias por ver",
    "suscribete",
    "gracias por su atencion",
    "www.",
    "subtitulos por",
)
AMBIENT_LABEL = re.compile(r"((musica|aplausos|risas|sigue|silencio)\W*)+")
BRACKETED = re.compile(r"[\[\(\*♪ ].*[\]\)\*♪ ]")


def wav_from_pcm(pcm: bytes) -> bytes:
    """Wrap 16 kHz mono 16-bit PCM in a minimal WAV container."""
    n = len(pcm)
    return (
        b"RIFF"
        + struct.pack("<I", 36 + n)
        + b"WAVEfmt "
        + struct.pack("<IHHIIHH", 16, 1, 1, SAMPLE_RATE, BYTES_PER_SECOND, 2, 16)
        + b"data"
        + struct.pack("<I", n)
        + pcm
    )


def rms(pcm: bytes) -> float:
    """Root-mean-square level of 16-bit PCM, sub-sampled for speed."""
    samples = array.array("h")
    samples.frombytes(pcm[: len(pcm) // 2 * 2])
    sub = samples[::16]
    return float((sum(x * x for x in sub) / max(1, len(sub))) ** 0.5)


def keep_segment(segment: dict[str, Any]) -> bool:
    """False for empty text, ambient labels, known Whisper hallucinations and low-confidence output."""
    text = (segment.get("text") or "").strip()
    low = normalize(text)
    return not (
        not text
        or BRACKETED.fullmatch(text)
        or any(h in low for h in HALLUCINATIONS)
        or AMBIENT_LABEL.fullmatch(low)
        or (segment.get("no_speech_prob") or 0) > 0.7
        or (segment.get("avg_logprob") or 0) < -1.3
    )


def multipart(fields: dict[str, str], wav: bytes) -> tuple[bytes, str]:
    """``multipart/form-data`` body for whisper-server's ``/inference``; returns ``(body, boundary)``."""
    boundary = "----tdt" + os.urandom(8).hex()
    parts = [
        f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode() for k, v in fields.items()
    ]
    parts.append(
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="a.wav"\r\n'
            "Content-Type: audio/wav\r\n\r\n"
        ).encode()
        + wav
        + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), boundary


class Whisper:
    """Client (and optional launcher) of a ``whisper-server`` process."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.lock = threading.Lock()
        self.proc: subprocess.Popen[bytes] | None = None
        self.last = 0.0
        self.state = "off"  # off | starting | ready | error
        self._launched_with: tuple[str, ...] = ()  # what the managed process was started with

    @property
    def binary(self) -> str:
        """The configured whisper-server, else one in the PATH, else one next to the models folder."""
        local_bin = self.config.models_dir.parent / "bin"
        return (
            self.config.whisper_bin
            or shutil.which("whisper-server")
            or shutil.which("whisper-server", path=str(local_bin))
            or str(local_bin / "whisper-server")
        )

    @property
    def model(self) -> str:
        """The configured model, else the first ``ggml-*.bin`` in the models folder."""
        return self.config.whisper_model or self._first_model(self.config.models_dir)

    @staticmethod
    def _first_model(models_dir: Path) -> str:
        found = sorted(models_dir.glob("ggml-*.bin")) if models_dir.is_dir() else []
        return str(found[0]) if found else ""

    def launch_settings(self) -> tuple[str, ...]:
        """Everything that, when changed, requires restarting the server we launched."""
        c = self.config
        return (self.binary, self.model, c.whisper_url, c.whisper_lang, str(c.whisper_threads))

    def reconfigure(self) -> None:
        """Settings changed: stop the server we launched if it was started with different ones."""
        with self.lock:
            if self.proc and self.proc.poll() is None and self._launched_with != self.launch_settings():
                log.info("ajustes de Whisper cambiados: se reinicia whisper-server")
                self.stop()
            self.state = "off" if not (self.proc and self.proc.poll() is None) else self.state

    def configured(self) -> bool:
        """True if we have what we need to launch a server ourselves."""
        return bool(self.binary and self.model and Path(self.binary).is_file() and Path(self.model).is_file())

    def is_up(self) -> bool:
        try:
            LOCAL_OPENER.open(self.config.whisper_url, timeout=2).close()
            return True
        except urllib.error.HTTPError:
            return True  # it answers, even if with a 404
        except Exception:
            return False

    def ensure(self) -> None:
        """Make sure a server answers, launching ours if needed (can take a while: the model is loaded)."""
        with self.lock:
            self.last = time.time()
            if self.is_up():
                self.state = "ready"
                return
            if not self.config.whisper_autostart:
                self.state = "error"
                raise RuntimeError(
                    f"no hay whisper-server en {self.config.whisper_url} (el arranque automático está desactivado)"
                )
            if not self.configured():
                self.state = "error"
                raise RuntimeError(
                    f"no hay whisper-server en {self.config.whisper_url} ni binario/modelo para lanzarlo"
                )
            self.state = "starting"
            if self.proc is None or self.proc.poll() is not None:
                port = urllib.parse.urlsplit(self.config.whisper_url).port or 8178
                log.info("iniciando whisper-server (%s)...", Path(self.model).name)
                self._launched_with = self.launch_settings()
                self.proc = subprocess.Popen(
                    [
                        self.binary,
                        "-m",
                        self.model,
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(port),
                        "-l",
                        self.config.whisper_lang,
                        "-t",
                        str(self.config.whisper_threads),
                        "-sns",
                        "-nth",
                        "0.6",
                    ],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=NO_WINDOW,
                )
            started = time.time()
            while time.time() - started < 120:
                if self.is_up():
                    self.state = "ready"
                    log.info("whisper-server listo (%.0f s)", time.time() - started)
                    return
                if self.proc.poll() is not None:
                    self.state = "error"
                    raise RuntimeError(f"whisper-server se cerró al arrancar (código {self.proc.returncode})")
                time.sleep(0.5)
            self.state = "error"
            raise RuntimeError("whisper-server no ha arrancado en 2 minutos")

    def transcribe(self, wav: bytes) -> list[list[Any]]:
        """``[[start, end, text], ...]`` in seconds, already without hallucinations and silences."""
        self.ensure()
        body, boundary = multipart(
            {
                "temperature": "0.0",
                "temperature_inc": "0.2",
                "response_format": "verbose_json",
                "language": self.config.whisper_lang,
            },
            wav,
        )
        request = urllib.request.Request(
            self.config.whisper_url.rstrip("/") + "/inference",
            data=body,
            headers={"Content-Type": "multipart/form-data; boundary=" + boundary},
        )
        with LOCAL_OPENER.open(request, timeout=90) as response:
            data = json.loads(response.read(2_000_000).decode("utf-8", "replace"))
        self.last = time.time()
        return [
            [round(float(s.get("start") or 0), 2), round(float(s.get("end") or 0), 2), (s.get("text") or "").strip()]
            for s in data.get("segments") or []
            if keep_segment(s)
        ]

    def idle_stop(self) -> None:
        with self.lock:
            if (
                self.proc
                and self.proc.poll() is None
                and time.time() - self.last > self.config.whisper_idle_minutes * 60
            ):
                log.info("whisper-server apagado por inactividad")
                self.stop()

    def stop(self) -> None:
        proc, self.proc = self.proc, None
        self.state = "off"
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(5)
            except subprocess.TimeoutExpired:
                proc.kill()


def diagnose(config: Config) -> dict[str, Any]:
    """What the given settings would find: ffmpeg, the whisper-server program, the model and a running server."""
    whisper = Whisper(config)
    binary, model = whisper.binary, whisper.model
    model_path = Path(model) if model else None
    return {
        "ffmpeg": shutil.which("ffmpeg") or "",
        "binary": {"path": binary, "found": Path(binary).is_file()},
        "model": {
            "path": model,
            "found": bool(model_path and model_path.is_file()),
            "bytes": model_path.stat().st_size if model_path and model_path.is_file() else 0,
        },
        "server_up": whisper.is_up(),
        "can_launch": whisper.configured(),
    }


class PcmStream:
    """Continuous audio (mp3/aac radio): bytes sent to the browser are copied into an ffmpeg that
    produces PCM, and every ``WINDOW_SECONDS`` a request goes to Whisper."""

    def __init__(self, hub: Transcriber, tag: str) -> None:
        self.hub = hub
        self.tag = tag
        self.proc = subprocess.Popen(
            [
                hub.ffmpeg,
                "-loglevel",
                "error",
                "-nostdin",
                "-i",
                "pipe:0",
                "-vn",
                "-ac",
                "1",
                "-ar",
                str(SAMPLE_RATE),
                "-f",
                "s16le",
                "pipe:1",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            creationflags=NO_WINDOW,
        )
        threading.Thread(target=self._read, daemon=True, name="pcm-reader").start()

    def write(self, chunk: bytes) -> None:
        stdin = self.proc.stdin
        try:
            if stdin is None:
                raise ValueError("ffmpeg no tiene entrada")
            stdin.write(chunk)
            stdin.flush()
        except (OSError, ValueError):
            self.close()

    def _read(self) -> None:
        stdout = self.proc.stdout
        if stdout is None:
            return
        need, buf = int(WINDOW_SECONDS * BYTES_PER_SECOND), bytearray()
        while True:
            block = stdout.read(8000)
            if not block:
                break
            buf += block
            if len(buf) >= need:
                self.hub.submit(self.tag, "", pcm=bytes(buf))
                buf.clear()
        self.close()

    def close(self) -> None:
        with contextlib.suppress(OSError):
            if self.proc.stdin:
                self.proc.stdin.close()
        with contextlib.suppress(OSError):
            self.proc.kill()


class Tap:
    """Copies the bytes the proxy sends to the browser so they can be transcribed."""

    def __init__(self, hub: Transcriber, tag: str, url: str, head: bytes, pcm: PcmStream | None) -> None:
        self.hub, self.tag, self.url, self.pcm = hub, tag, url, pcm
        self.buffer: bytearray | None = None if pcm else bytearray(head)
        if pcm and head:
            pcm.write(head)

    def feed(self, chunk: bytes) -> None:
        if self.buffer is not None:
            if len(self.buffer) < MAX_SEGMENT_BYTES:
                self.buffer += chunk
        elif self.pcm is not None:
            self.pcm.write(chunk)

    def finish(self) -> None:
        """A complete HLS segment has been served: queue it."""
        if self.buffer:
            self.hub.submit(self.tag, self.url, data=bytes(self.buffer))


class Transcriber:
    """Sessions (one per playing tile), the job queue and the worker thread."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.ffmpeg = shutil.which("ffmpeg") or ""
        self.whisper = Whisper(config)
        self.stop_event = threading.Event()
        self._sessions: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=QUEUE_SIZE)
        self._worker: threading.Thread | None = None
        self._availability: tuple[float, bool] = (0.0, False)

    def reconfigure(self) -> None:
        """Apply changed settings: restart our whisper-server if needed and forget the cached availability."""
        self.whisper.reconfigure()
        self._availability = (0.0, False)

    def available(self) -> bool:
        """ffmpeg is installed and a Whisper server is running or can be launched.

        Probing a server that is not there can take seconds on some systems, so the answer is cached.
        """
        if not (self.config.stt_enabled and self.ffmpeg):
            return False
        checked, value = self._availability
        if time.time() - checked > AVAILABILITY_TTL:
            value = self.whisper.configured() or self.whisper.is_up()
            self._availability = (time.time(), value)
        return value

    # ---- sessions
    def is_active(self, tag: str) -> bool:
        with self._lock:
            return tag in self._sessions

    def set_session(self, tag: str, on: bool) -> None:
        tag = (tag or "")[:40]
        if not tag:
            return
        with self._lock:
            session = self._sessions.get(tag)
            if on:
                if session is None:
                    self._sessions[tag] = {
                        "seq": 0,
                        "items": collections.deque(maxlen=300),
                        "pcm": None,
                        "seen": time.time(),
                        "err": "",
                    }
                else:
                    session["seen"] = time.time()
                if self._worker is None:
                    self._worker = threading.Thread(target=self._work, daemon=True, name="stt-worker")
                    self._worker.start()
            elif session is not None:
                self._sessions.pop(tag, None)
                if session["pcm"]:
                    session["pcm"].close()

    def tap(self, tag: str, url: str, ctype: str, has_length: bool, head: bytes) -> Tap | None:
        """A :class:`Tap` for this response if the browser enabled transcription for ``tag``."""
        if not tag:
            return None
        live = ctype.lower().startswith("audio/") and not has_length
        with self._lock:
            session = self._sessions.get(tag)
            if session is None:
                return None
            pcm = None
            if live:
                if not self.ffmpeg:
                    return None
                if session["pcm"] is None:
                    session["pcm"] = PcmStream(self, tag)
                pcm = session["pcm"]
        return Tap(self, tag, url, head, pcm)

    def poll(self, tag: str, after: int) -> dict[str, Any]:
        with self._lock:
            session = self._sessions.get(tag)
            if session is None:
                return {"items": [], "err": "", "whisper": self.whisper.state, "active": False}
            session["seen"] = time.time()
            return {
                "items": [i for i in session["items"] if i["seq"] > after],
                "err": session["err"],
                "whisper": self.whisper.state,
                "queued": self._queue.qsize(),
                "active": True,
            }

    # ---- work
    def submit(self, tag: str, url: str, data: bytes | None = None, pcm: bytes | None = None) -> None:
        job = {"tag": tag, "u": url, "data": data, "pcm": pcm}
        try:
            self._queue.put_nowait(job)
        except queue.Full:  # live audio: old work is useless, drop the oldest job
            with contextlib.suppress(queue.Empty):
                self._queue.get_nowait()
            with contextlib.suppress(queue.Full):
                self._queue.put_nowait(job)

    def decode(self, data: bytes) -> bytes:
        """Any audio container -> 16 kHz mono PCM through ffmpeg."""
        result = subprocess.run(
            [
                self.ffmpeg,
                "-loglevel",
                "error",
                "-nostdin",
                "-i",
                "pipe:0",
                "-vn",
                "-ac",
                "1",
                "-ar",
                str(SAMPLE_RATE),
                "-f",
                "s16le",
                "pipe:1",
            ],
            input=data,
            capture_output=True,
            timeout=40,
            creationflags=NO_WINDOW,
            check=False,
        )
        return result.stdout

    def _reap_idle_sessions(self) -> None:
        now = time.time()
        with self._lock:
            for key in [k for k, v in self._sessions.items() if now - v["seen"] > SESSION_TTL]:
                session = self._sessions.pop(key)
                if session["pcm"]:
                    session["pcm"].close()

    def _work(self) -> None:
        while not self.stop_event.is_set():
            try:
                job = self._queue.get(timeout=5)
            except queue.Empty:
                self.whisper.idle_stop()
                self._reap_idle_sessions()
                continue
            with self._lock:
                session = self._sessions.get(job["tag"])
            if session is None:
                continue
            try:
                pcm = job["pcm"] if job["pcm"] is not None else self.decode(job["data"])
                duration = len(pcm) / BYTES_PER_SECOND
                silent = duration < MIN_SECONDS or rms(pcm) < MIN_RMS
                segments = [] if silent else self.whisper.transcribe(wav_from_pcm(pcm))
            except Exception as exc:
                with self._lock:
                    session["err"] = f"{type(exc).__name__}: {exc}"
                log.warning("transcripción: %s", session["err"])
                self.stop_event.wait(1)
                continue
            with self._lock:
                session["seq"] += 1
                session["err"] = ""
                session["items"].append(
                    {"seq": session["seq"], "u": job["u"], "dur": round(duration, 2), "segs": segments}
                )

    def close(self) -> None:
        self.stop_event.set()
        with self._lock:
            for session in self._sessions.values():
                if session["pcm"]:
                    session["pcm"].close()
            self._sessions.clear()
        self.whisper.stop()
