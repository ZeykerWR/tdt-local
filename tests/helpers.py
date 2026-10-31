"""Test fixtures: a scriptable fake origin and a fully wired application on a temporary directory."""

from __future__ import annotations

import http.client
import json
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, ClassVar

from tdtlocal.app import App
from tdtlocal.config import PROJECT_DIR, Config
from tdtlocal.server import TdtServer, create_server

FIXTURES = Path(__file__).parent / "fixtures"

Response = tuple  # (status, headers dict, body bytes)
Route = Callable[[BaseHTTPRequestHandler], Response]


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class FakeOrigin:
    """A tiny HTTP server on 127.0.0.1 whose routes the test registers.

    ``routes[path]`` is either a ``(status, headers, body)`` tuple or a callable receiving the request handler
    and returning one. Every request is recorded in ``requests`` as ``(path, headers)``.
    """

    def __init__(self) -> None:
        self.routes: dict[str, Response | Route] = {}
        self.requests: list[tuple[str, dict[str, str]]] = []
        self.bodies: list[bytes] = []  # request bodies, in order
        origin = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: Any) -> None:
                pass

            def _serve(self) -> None:
                path = self.path
                origin.requests.append((path, {k.lower(): v for k, v in self.headers.items()}))
                length = int(self.headers.get("Content-Length") or 0)
                origin.bodies.append(self.rfile.read(length) if length else b"")
                route = origin.routes.get(path.split("?")[0]) or origin.routes.get(path)
                if route is None:
                    status, headers, body = 404, {}, b"not found"
                else:
                    status, headers, body = route(self) if callable(route) else route
                self.send_response(status)
                for key, value in headers.items():
                    self.send_header(key, value)
                if "Content-Length" not in headers:
                    self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(body)

            do_GET = do_POST = do_HEAD = _serve

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.httpd.daemon_threads = True
        self.thread = threading.Thread(target=self.httpd.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        self.thread.start()

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def url(self, path: str) -> str:
        return self.base + path

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


def make_tv_markdown(count: int = 60, base: str = "https://tv.example") -> str:
    """A ``TELEVISION.md`` with ``count`` channels in one category."""
    rows = [
        "## Nacionales",
        "| Canal | M3U8 | Web | Logo | EPG ID | Info |",
        "|-------|------|-----|------|--------|------|",
    ]
    for i in range(count):
        rows.append(
            f"| Canal {i} | [Opción 1]({base}/{i}/index.m3u8) | [Web]({base}/web/{i}) | [Logo]({base}/logo/{i}.png)"
            f" | Canal{i}.TV | - |"
        )
    return "\n".join(rows) + "\n"


class AppCase(unittest.TestCase):
    """Base class: temporary data dir, an application (no background threads) and optional fake origin."""

    config_overrides: ClassVar[dict[str, Any]] = {}

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.origin = FakeOrigin()
        self.addCleanup(self.origin.close)
        self.app = self.make_app()

    def make_app(self, **overrides: Any) -> App:
        values: dict[str, Any] = {
            "data_dir": self.tmp / "data",
            "models_dir": self.tmp / "models",
            "port": 0,
            "allow_private": True,
            "locked": frozenset({"models_dir"}),  # chosen by the test, as a command-line flag would
            "ai_enabled": True,
            "stt_enabled": False,  # probing a Whisper server is slow on some systems; tests opt in
        }
        values.update(self.config_overrides)
        values.update(overrides)
        app = App(Config(**values))
        self.addCleanup(app.close)
        return app


class ServerCase(AppCase):
    """An :class:`AppCase` with the HTTP server running on an ephemeral port."""

    def setUp(self) -> None:
        super().setUp()
        self.httpd: TdtServer = create_server(self.app)
        threading.Thread(target=self.httpd.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True).start()
        self.addCleanup(self._stop_server)
        self.port = self.httpd.server_address[1]

    def _stop_server(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()

    def request(
        self, method: str, path: str, body: Any = None, headers: dict[str, str] | None = None
    ) -> tuple[int, dict[str, str], bytes]:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            payload = json.dumps(body).encode() if body is not None else None
            hdrs = dict(headers or {})
            if payload is not None:
                hdrs.setdefault("Content-Type", "application/json")
            conn.request(method, path, body=payload, headers=hdrs)
            response = conn.getresponse()
            return response.status, {k.lower(): v for k, v in response.getheaders()}, response.read()
        finally:
            conn.close()

    def get_json(self, path: str, **kwargs: Any) -> tuple[int, Any]:
        status, _, data = self.request("GET", path, **kwargs)
        return status, json.loads(data.decode("utf-8"))

    def post_json(self, path: str, body: Any = None, **kwargs: Any) -> tuple[int, Any]:
        status, _, data = self.request("POST", path, body if body is not None else {}, **kwargs)
        return status, json.loads(data.decode("utf-8"))


# ---- real server processes (end to end tests)
NO_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # the system proxy must not see loopback


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class ServerProcess:
    """``python -m tdtlocal`` running for real. Its output goes to a file shown when a test fails."""

    def __init__(self, case: unittest.TestCase, data_dir: str, *args: str) -> None:
        self.port = free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        self.log_path = Path(data_dir) / "server-output.log"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log = self.log_path.open("wb")
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "tdtlocal", "--port", str(self.port), "--data-dir", data_dir, *args],
            cwd=PROJECT_DIR,
            stdout=self._log,
            stderr=subprocess.STDOUT,
        )
        case.addCleanup(self._stop)

    def _stop(self) -> None:
        """Kill the process and wait for it, so that Windows lets the temporary folder be removed."""
        self.proc.kill()
        self.proc.wait(10)
        self._log.close()

    def output(self) -> str:
        self._log.flush()
        return self.log_path.read_text(encoding="utf-8", errors="replace")

    def get(self, path: str, timeout: float = 5) -> tuple[int, bytes]:
        with NO_PROXY.open(self.base + path, timeout=timeout) as response:
            return response.status, response.read()

    def get_json_when(self, path: str, ready: Callable[[Any], bool] = lambda data: True, timeout: float = 40) -> Any:
        """Poll ``path`` until ``ready(data)``; fail with the server's own output if it never happens."""
        end = time.time() + timeout
        last: Exception | None = None
        while time.time() < end:
            if self.proc.poll() is not None:
                raise AssertionError(f"the server exited with code {self.proc.returncode}:\n{self.output()}")
            try:
                data = json.loads(self.get(path)[1])
                if ready(data):
                    return data
            except OSError as exc:
                last = exc
            time.sleep(0.2)
        raise AssertionError(
            f"{path} not ready after {timeout:.0f} s (last error: {last!r}). Server output:\n{self.output()}"
        )
