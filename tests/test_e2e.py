"""End to end: the real command (``python -m tdtlocal``) against a fake list server."""

import json
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

from tdtlocal.config import PROJECT_DIR

from .helpers import FakeOrigin, fixture, make_tv_markdown


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class CommandLineTests(unittest.TestCase):
    def test_server_starts_downloads_the_lists_and_stops_cleanly(self):
        origin = FakeOrigin()
        self.addCleanup(origin.close)
        radio = fixture("RADIO.md") + "\n".join(
            f"| R{i} | [mp3](https://r.example/{i}.mp3) | - | - | - | - |" for i in range(40)
        )
        origin.routes["/TELEVISION.md"] = (200, {}, make_tv_markdown(60).encode())
        origin.routes["/RADIO.md"] = (200, {}, radio.encode())
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        port = free_port()
        proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "tdtlocal",
                "--port",
                str(port),
                "--data-dir",
                tmp.name,
                "--no-epg",
                "--no-ai",
                "--no-stt",
                "--source",
                origin.url("/TELEVISION.md"),
                "--radio-source",
                origin.url("/RADIO.md"),
            ],
            cwd=PROJECT_DIR,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.addCleanup(proc.kill)
        base = f"http://127.0.0.1:{port}"

        def fetch(path):
            with urllib.request.urlopen(base + path, timeout=5) as response:
                return response.status, response.read()

        data = None
        deadline = time.time() + 20
        while time.time() < deadline:
            try:
                _, body = fetch("/api/channels")
                data = json.loads(body)
                if len(data["channels"]) >= 60:
                    break
            except OSError:
                pass
            time.sleep(0.2)
        self.assertIsNotNone(data, "the server never answered")
        self.assertEqual(len([c for c in data["channels"] if c["kind"] == "tv"]), 60)
        self.assertEqual(len([c for c in data["channels"] if c["kind"] == "radio"]), 42)
        self.assertFalse(data["meta"]["ai"])
        self.assertFalse(data["meta"]["stt"])
        self.assertEqual(fetch("/")[0], 200)
        self.assertTrue((Path(tmp.name) / "tv.json").exists())  # the cache for the next start

        proc.terminate()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            self.fail("the server did not stop after SIGTERM")

    def test_a_busy_port_is_reported_instead_of_a_traceback(self):
        with socket.socket() as taken:
            taken.bind(("127.0.0.1", 0))
            taken.listen()
            port = taken.getsockname()[1]
            tmp = tempfile.TemporaryDirectory()
            self.addCleanup(tmp.cleanup)
            result = subprocess.run(
                [sys.executable, "-m", "tdtlocal", "--port", str(port), "--data-dir", tmp.name, "--no-epg"],
                cwd=PROJECT_DIR,
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--port", result.stderr)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
