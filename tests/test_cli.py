import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from tdtlocal import __version__
from tdtlocal.cli import build_parser, config_from_args
from tdtlocal.config import DEFAULT_PORT, EPG_SOURCES


class CliTests(unittest.TestCase):
    def config(self, *argv, env=None):
        with mock.patch.dict("os.environ", env or {}, clear=False):
            return config_from_args(build_parser().parse_args(list(argv)))

    def test_defaults_are_safe(self):
        config = self.config()
        self.assertEqual((config.host, config.port), ("127.0.0.1", DEFAULT_PORT))
        self.assertTrue(config.loopback_only)
        self.assertFalse(config.allow_private)
        self.assertEqual(config.epg_sources, EPG_SOURCES)
        self.assertTrue(config.ai_enabled and config.stt_enabled and config.epg_enabled)

    def test_lan_listens_everywhere_and_disables_the_host_check(self):
        config = self.config("--lan")
        self.assertEqual(config.host, "0.0.0.0")  # noqa: S104
        self.assertFalse(config.loopback_only)

    def test_options(self):
        config = self.config(
            "--port",
            "9000",
            "--interval",
            "2",
            "--no-ai",
            "--no-stt",
            "--no-epg",
            "--auto-check",
            "--llm-url",
            "http://llm:1/v1",
            "--llm-model",
            "m",
            "--whisper-lang",
            "en",
            "--epg-source",
            "http://e/tv.xml",
            "--radio-epg-source",
            "http://e/r.xml",
        )
        self.assertEqual((config.port, config.update_hours, config.update_seconds), (9000, 2, 7200))
        self.assertFalse(config.ai_enabled or config.stt_enabled or config.epg_enabled)
        self.assertTrue(config.auto_check)
        self.assertEqual((config.llm_url, config.llm_model, config.whisper_lang), ("http://llm:1/v1", "m", "en"))
        self.assertEqual(config.epg_sources, {"tv": "http://e/tv.xml", "radio": "http://e/r.xml"})

    def test_environment_provides_defaults_and_flags_override_them(self):
        env = {
            "TDT_LLM_URL": "http://env:8080/v1",
            "TDT_WHISPER_BIN": "/opt/whisper-server",
            "TDT_DATA_DIR": str(Path.cwd() / "somewhere"),
        }
        config = self.config(env=env)
        self.assertEqual(config.llm_url, "http://env:8080/v1")
        self.assertEqual(config.whisper_bin, "/opt/whisper-server")
        self.assertEqual(config.data_dir, (Path.cwd() / "somewhere").resolve())
        self.assertEqual(self.config("--llm-url", "http://flag/v1", env=env).llm_url, "http://flag/v1")

    def test_version_flag(self):
        out = io.StringIO()
        with redirect_stdout(out), self.assertRaises(SystemExit) as ctx:
            build_parser().parse_args(["--version"])
        self.assertEqual(ctx.exception.code, 0)
        self.assertIn(__version__, out.getvalue())

    def test_unknown_flag_is_an_error(self):
        with self.assertRaises(SystemExit), mock.patch("sys.stderr", new=io.StringIO()):
            build_parser().parse_args(["--nope"])


if __name__ == "__main__":
    unittest.main()
