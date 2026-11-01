"""The sound chain that the bridge extension loads is made from the page's own code, and must not fall behind it."""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("build_bridge", ROOT / "scripts" / "build_bridge.py")
build_bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build_bridge)  # type: ignore[union-attr]


class BuildBridgeTests(unittest.TestCase):
    def test_the_committed_file_is_up_to_date(self):
        self.assertEqual(
            build_bridge.OUT.read_text(encoding="utf-8"),
            build_bridge.build(),
            "tools/puente-atresplayer/audio-chain.js está desfasado: ejecuta python scripts/build_bridge.py",
        )

    def test_it_is_plain_script_that_publishes_what_the_bridge_uses(self):
        text = build_bridge.build()
        self.assertNotRegex(text, r"(?m)^(import|export) ")
        self.assertIn("globalThis.TDT_AUDIO = {", text)
        for name in ("chainFor", "wake", "sanitize"):
            self.assertRegex(text, rf"(?m)^(async )?function {name}\b")

    @unittest.skipUnless(shutil.which("node"), "node no está instalado")
    def test_it_is_valid_javascript_and_has_no_name_clashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "chain.js"
            target.write_text(build_bridge.build(), encoding="utf-8")
            done = subprocess.run(["node", "--check", str(target)], capture_output=True, text=True, check=False)
        self.assertEqual(done.returncode, 0, done.stderr)


if __name__ == "__main__":
    unittest.main()
