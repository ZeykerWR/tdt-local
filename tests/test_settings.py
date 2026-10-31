import hashlib
import json
import os
import threading
import time
import unittest
import urllib.error
from typing import ClassVar
from unittest import mock

from tdtlocal import settings as settings_module
from tdtlocal import whisper_models
from tdtlocal.ai import ModelError
from tdtlocal.cli import build_parser, config_from_args
from tdtlocal.config import Config
from tdtlocal.settings import BY_NAME, FIELDS, SettingsStore

from .helpers import AppCase, ServerCase


class FieldValidationTests(unittest.TestCase):
    def check(self, name, value):
        return BY_NAME[name].validate(value)

    def test_every_field_accepts_its_own_default(self):
        for f in FIELDS:
            self.assertEqual(f.validate(f.default), f.default, msg=f.name)

    def test_booleans_must_be_booleans(self):
        for bad in ("true", 1, None, "si"):
            with self.assertRaises(ValueError, msg=repr(bad)):
                self.check("ai_enabled", bad)

    def test_numbers_are_range_checked_and_coerced(self):
        self.assertEqual(self.check("llm_max_tokens", 300), 300)
        self.assertEqual(self.check("llm_temperature", 1), 1.0)
        for name, bad in (
            ("llm_max_tokens", 5),
            ("llm_max_tokens", 99999),
            ("llm_max_tokens", 12.5),
            ("llm_temperature", 3),
            ("llm_temperature", -0.1),
            ("llm_temperature", "0.2"),
            ("llm_temperature", True),
            ("llm_temperature", float("nan")),
            ("llm_temperature", float("inf")),
            ("whisper_threads", 0),
        ):
            with self.assertRaises(ValueError, msg=f"{name}={bad!r}"):
                self.check(name, bad)

    def test_urls_must_be_http(self):
        self.assertEqual(self.check("llm_url", "  http://127.0.0.1:8080/v1  "), "http://127.0.0.1:8080/v1")
        for bad in (
            "",
            "ftp://x/y",
            "javascript:alert(1)",
            "localhost:8080",
            "http://a b/c",
            5,
            "http://x/" + "a" * 500,
        ):
            with self.assertRaises(ValueError, msg=repr(bad)):
                self.check("llm_url", bad)

    def test_text_cannot_hold_line_breaks(self):
        self.assertEqual(self.check("llm_model", " qwen "), "qwen")
        for bad in ("a\nb", "a\x00b", "x" * 500, 5):
            with self.assertRaises(ValueError, msg=repr(bad)):
                self.check("llm_model", bad)

    def test_choices(self):
        self.assertEqual(self.check("whisper_lang", "auto"), "auto")
        with self.assertRaises(ValueError):
            self.check("whisper_lang", "klingon")

    def test_extra_params_must_be_a_json_object_without_reserved_keys(self):
        self.assertEqual(self.check("llm_extra_params", ' {"top_p": 0.9} '), '{"top_p": 0.9}')
        self.assertEqual(self.check("llm_extra_params", "  "), "")
        for bad in ("{no", "[1]", "5", '{"messages": []}', '{"stream": true}', "x" * 5000):
            with self.assertRaises(ValueError, msg=bad):
                self.check("llm_extra_params", bad)


class SettingsStoreTests(AppCase):
    def make(self, **config):
        locked = frozenset(config.pop("locked", frozenset())) | {"models_dir"}  # given by the caller, like a flag
        cfg = Config(data_dir=self.tmp / "d", models_dir=self.tmp / "m", locked=locked, **config)
        return cfg, SettingsStore(cfg)

    def saved(self, store):
        return json.loads(store.path.read_text(encoding="utf-8"))

    def test_snapshot_has_values_defaults_and_never_the_secret(self):
        cfg, store = self.make(llm_api_key="sk-secret")
        snap = store.snapshot()
        self.assertEqual(snap["values"]["llm_url"], cfg.llm_url)
        self.assertEqual(snap["values"]["llm_api_key"], "")
        self.assertEqual(snap["secrets_set"], {"llm_api_key": True})
        self.assertNotIn("llm_api_key", snap["defaults"])
        self.assertNotIn("sk-secret", json.dumps(snap))
        self.assertEqual(snap["limits"]["llm_temperature"], {"min": 0, "max": 2, "choices": []})
        self.assertIn("es", snap["limits"]["whisper_lang"]["choices"])

    def test_update_applies_persists_only_non_defaults_and_reports_changes(self):
        cfg, store = self.make()
        changed, errors = store.update({"llm_model": "qwen", "llm_temperature": 0.7, "whisper_lang": "es"})
        self.assertEqual((sorted(changed), errors), (["llm_model", "llm_temperature"], {}))
        self.assertEqual((cfg.llm_model, cfg.llm_temperature), ("qwen", 0.7))
        self.assertEqual(self.saved(store)["values"], {"llm_model": "qwen", "llm_temperature": 0.7})
        self.assertEqual(store.update({"llm_model": "qwen"}), ([], {}))  # nothing changed

    def test_saved_values_survive_a_restart(self):
        cfg, store = self.make()
        store.update(
            {
                "llm_url": "http://10.0.0.5:9/v1",
                "stt_enabled": False,
                "epg_tv_source": "http://x/tv.xml",
                "llm_api_key": "sk-1",
            }
        )
        again, store2 = self.make()
        store2.load()
        self.assertEqual(again.llm_url, "http://10.0.0.5:9/v1")
        self.assertFalse(again.stt_enabled)
        self.assertEqual(again.epg_sources, {"tv": "http://x/tv.xml", "radio": cfg.epg_sources["radio"]})
        self.assertEqual(again.llm_api_key, "sk-1")

    def test_an_invalid_change_applies_nothing(self):
        cfg, store = self.make()
        changed, errors = store.update({"llm_model": "ok", "llm_max_tokens": 1, "nope": 1})
        self.assertEqual(changed, [])
        self.assertEqual(set(errors), {"llm_max_tokens", "nope"})
        self.assertEqual(cfg.llm_model, "")
        self.assertFalse(store.path.exists())

    def test_secret_semantics_null_keeps_empty_clears(self):
        cfg, store = self.make()
        store.update({"llm_api_key": "sk-1"})
        store.update({"llm_api_key": None, "llm_model": "m"})
        self.assertEqual(cfg.llm_api_key, "sk-1")
        store.update({"llm_api_key": ""})
        self.assertEqual(cfg.llm_api_key, "")
        self.assertNotIn("llm_api_key", self.saved(store)["values"])

    @unittest.skipIf(os.name == "nt", "POSIX permissions")
    def test_the_file_is_private(self):
        _, store = self.make()
        store.update({"llm_api_key": "sk-1"})
        self.assertEqual(store.path.stat().st_mode & 0o777, 0o600)

    def test_locked_settings_are_read_only_and_never_saved(self):
        cfg, store = self.make(llm_url="http://cli/v1", locked=frozenset({"llm_url"}))
        self.assertEqual(store.snapshot()["locked"], ["llm_url", "models_dir"])
        changed, errors = store.update({"llm_url": "http://other/v1"})
        self.assertEqual((changed, list(errors)), ([], ["llm_url"]))
        self.assertEqual(cfg.llm_url, "http://cli/v1")
        store.update({"llm_model": "m"})
        self.assertNotIn("llm_url", self.saved(store)["values"])

    def test_load_skips_locked_unknown_and_invalid_entries(self):
        _, writer = self.make()
        writer.path.parent.mkdir(parents=True)
        writer.path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "values": {
                        "llm_url": "http://saved/v1",
                        "llm_max_tokens": 999999,
                        "mystery": 1,
                        "llm_model": "kept",
                    },
                }
            ),
            encoding="utf-8",
        )
        cfg, store = self.make(llm_url="http://cli/v1", locked=frozenset({"llm_url"}))
        store.load()
        self.assertEqual((cfg.llm_url, cfg.llm_max_tokens, cfg.llm_model), ("http://cli/v1", 700, "kept"))

    def test_load_tolerates_a_corrupt_file(self):
        cfg, store = self.make()
        store.path.parent.mkdir(parents=True)
        for text in ("{no json", "[]", '{"values": 5}', ""):
            store.path.write_text(text, encoding="utf-8")
            store.load()
            self.assertEqual(cfg.llm_model, "")

    def test_reset_a_section_or_everything(self):
        cfg, store = self.make()
        store.update({"llm_model": "m", "whisper_lang": "en", "update_hours": 2.0})
        self.assertEqual(store.reset("ai"), ["llm_model"])
        self.assertEqual((cfg.llm_model, cfg.whisper_lang, cfg.update_hours), ("", "en", 2.0))
        self.assertEqual(sorted(store.reset()), ["update_hours", "whisper_lang"])
        self.assertEqual(self.saved(store)["values"], {})

    def test_reset_leaves_locked_settings_alone(self):
        cfg, store = self.make(llm_model="fixed", locked=frozenset({"llm_model"}))
        self.assertEqual(store.reset("ai"), [])
        self.assertEqual(cfg.llm_model, "fixed")

    def test_the_app_loads_settings_before_building_its_services(self):
        _, store = self.make()
        store.update({"whisper_lang": "en", "llm_max_tokens": 321})
        app = self.make_app(data_dir=self.tmp / "d")
        self.assertEqual((app.config.whisper_lang, app.config.llm_max_tokens), ("en", 321))

    def test_apply_settings_notifies_only_the_affected_services(self):
        app = self.app
        with (
            mock.patch.object(app.transcriber, "reconfigure") as stt,
            mock.patch.object(app.epg, "refresh_soon") as epg,
            mock.patch.object(app.feeds, "refresh_soon") as feeds,
        ):
            app.apply_settings(["llm_model", "update_hours"])
            self.assertEqual((stt.call_count, epg.call_count, feeds.call_count), (0, 0, 0))
            app.apply_settings(["whisper_model"])
            self.assertEqual((stt.call_count, epg.call_count, feeds.call_count), (1, 0, 0))
            app.apply_settings(["epg_enabled", "tv_source"])
            self.assertEqual((stt.call_count, epg.call_count, feeds.call_count), (1, 1, 1))

    def test_every_field_belongs_to_a_known_section(self):
        self.assertTrue({f.section for f in FIELDS} <= set(settings_module.SECTIONS))
        self.assertEqual(len({f.name for f in FIELDS}), len(FIELDS))


class CommandLinePrecedenceTests(unittest.TestCase):
    def config(self, *argv, env=None):
        return config_from_args(build_parser().parse_args(list(argv)), env or {})

    def test_nothing_given_locks_nothing(self):
        self.assertEqual(self.config().locked, frozenset())

    def test_flags_and_environment_lock_what_they_set(self):
        config = self.config(
            "--llm-url",
            "http://x/v1",
            "--no-ai",
            "--interval",
            "2",
            env={"TDT_LLM_API_KEY": "sk-env", "TDT_WHISPER_THREADS": "4", "TDT_STT_ENABLED": "no"},
        )
        self.assertEqual(
            config.locked, {"llm_url", "ai_enabled", "update_hours", "llm_api_key", "whisper_threads", "stt_enabled"}
        )
        self.assertEqual((config.llm_api_key, config.whisper_threads, config.stt_enabled), ("sk-env", 4, False))
        self.assertFalse(config.ai_enabled)

    def test_a_flag_beats_the_environment(self):
        config = self.config("--llm-model", "flag", env={"TDT_LLM_MODEL": "env"})
        self.assertEqual(config.llm_model, "flag")

    def test_invalid_values_stop_with_a_message_naming_the_source(self):
        for argv, env, source in (
            (["--interval", "0"], {}, "--interval"),
            (["--llm-url", "not a url"], {}, "--llm-url"),
            ([], {"TDT_WHISPER_THREADS": "many"}, "TDT_WHISPER_THREADS"),
            ([], {"TDT_AI_ENABLED": "perhaps"}, "TDT_AI_ENABLED"),
        ):
            with self.assertRaises(SystemExit) as ctx:
                self.config(*argv, env=env)
            self.assertIn(source, str(ctx.exception), msg=argv or env)


class AssistantParametersTests(AppCase):
    def setUp(self):
        super().setUp()
        self.app = self.make_app(llm_url=self.origin.url("/v1"))
        self.config = self.app.config
        self.assistant = self.app.assistant

    def body(self, **kw):
        return self.assistant.request_body([{"role": "user", "content": "hi"}], **kw)

    def test_defaults_match_what_the_assistant_always_sent(self):
        body = self.body()
        self.assertEqual((body["temperature"], body["max_tokens"]), (0.2, 700))
        self.assertEqual(body["chat_template_kwargs"], {"enable_thinking": False})
        self.assertEqual(body["reasoning_effort"], "none")
        self.assertNotIn("model", body)

    def test_settings_change_the_request(self):
        self.config.llm_temperature, self.config.llm_max_tokens, self.config.llm_model = 0.9, 123, "qwen"
        self.config.llm_disable_thinking = False
        body = self.body()
        self.assertEqual((body["temperature"], body["max_tokens"], body["model"]), (0.9, 123, "qwen"))
        self.assertNotIn("chat_template_kwargs", body)
        self.assertNotIn("reasoning_effort", body)
        self.assertEqual(self.body(max_tokens=50)["max_tokens"], 50)

    def test_extra_params_are_merged_but_cannot_replace_the_conversation(self):
        self.config.llm_extra_params = '{"top_p": 0.8, "temperature": 0.5, "messages": "x", "stream": true}'
        body = self.body()
        self.assertEqual((body["top_p"], body["temperature"]), (0.8, 0.5))
        self.assertIsInstance(body["messages"], list)
        self.assertNotIn("stream", body)
        self.config.llm_extra_params = "{broken"  # a corrupt saved value must not break the assistant
        self.assertEqual(self.body()["max_tokens"], 700)

    def test_api_key_is_sent_as_a_bearer_token(self):
        self.origin.routes["/v1/chat/completions"] = (
            200,
            {},
            b'{"choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}]}',
        )
        self.assistant.chat([{"role": "user", "content": "hi"}])
        self.assertNotIn("authorization", self.origin.requests[-1][1])
        self.config.llm_api_key = "sk-123"
        self.assistant.chat([{"role": "user", "content": "hi"}])
        self.assertEqual(self.origin.requests[-1][1]["authorization"], "Bearer sk-123")

    def test_list_models(self):
        self.origin.routes["/v1/models"] = (
            200,
            {},
            b'{"data": [{"id": "a"}, {"id": "b", "object": "model"}, {"nope": 1}, "x"]}',
        )
        self.assertEqual(self.assistant.list_models(), ["a", "b"])
        self.assertEqual(self.assistant.list_models(self.origin.url("/v1"), "key-x"), ["a", "b"])
        self.assertEqual(self.origin.requests[-1][1]["authorization"], "Bearer key-x")
        self.origin.routes["/v1/models"] = (200, {}, b'{"models": []}')
        with self.assertRaises(ModelError):
            self.assistant.list_models()

    def test_the_timeout_comes_from_the_settings(self):
        self.config.llm_timeout = 7
        with mock.patch("tdtlocal.ai.LOCAL_OPENER.open", side_effect=urllib.error.URLError("x")) as opener:
            with self.assertRaises(urllib.error.URLError):
                self.assistant.chat([])
            self.assertEqual(opener.call_args.kwargs["timeout"], 7)


class WhisperSettingsTests(AppCase):
    def setUp(self):
        super().setUp()
        (self.tmp / "models").mkdir()
        self.model = self.tmp / "models" / "ggml-x.bin"
        self.model.write_bytes(b"m")
        self.binary = self.tmp / "ws.exe"
        self.binary.write_bytes(b"b")
        self.app = self.make_app(whisper_bin=str(self.binary), whisper_url="http://127.0.0.1:9")
        self.whisper = self.app.transcriber.whisper

    def test_paths_follow_the_settings_live(self):
        self.assertEqual((self.whisper.binary, self.whisper.model), (str(self.binary), str(self.model)))
        other = self.tmp / "other.bin"
        other.write_bytes(b"o")
        self.app.config.whisper_model = str(other)
        self.assertEqual(self.whisper.model, str(other))
        self.app.config.whisper_model = ""
        self.assertEqual(self.whisper.model, str(self.model))

    def test_autostart_can_be_disabled(self):
        self.app.config.whisper_autostart = False
        with (
            mock.patch.object(self.whisper, "is_up", return_value=False),
            self.assertRaisesRegex(RuntimeError, "arranque automático está desactivado"),
        ):
            self.whisper.ensure()
        self.assertEqual(self.whisper.state, "error")

    def test_launch_arguments_use_threads_and_language(self):
        self.app.config.whisper_threads, self.app.config.whisper_lang = 3, "auto"
        proc = mock.MagicMock()
        proc.poll.return_value = None
        with (
            mock.patch.object(self.whisper, "is_up", side_effect=[False, True]),
            mock.patch("tdtlocal.stt.subprocess.Popen", return_value=proc) as popen,
        ):
            self.whisper.ensure()
        args = popen.call_args.args[0]
        self.assertEqual(args[args.index("-t") + 1], "3")
        self.assertEqual(args[args.index("-l") + 1], "auto")
        self.assertEqual(args[args.index("-m") + 1], str(self.model))

    def test_reconfigure_restarts_the_server_only_when_launch_settings_changed(self):
        proc = mock.MagicMock()
        proc.poll.return_value = None
        self.whisper.proc, self.whisper._launched_with = proc, self.whisper.launch_settings()
        self.whisper.reconfigure()
        proc.terminate.assert_not_called()
        self.app.config.whisper_threads = 2
        self.whisper.reconfigure()
        proc.terminate.assert_called_once()
        self.assertIsNone(self.whisper.proc)

    def test_idle_timeout_is_in_minutes_from_the_settings(self):
        proc = mock.MagicMock()
        proc.poll.return_value = None
        self.whisper.proc = proc
        self.whisper.last = time.time() - 90
        self.whisper.idle_stop()
        proc.terminate.assert_not_called()
        self.app.config.whisper_idle_minutes = 1
        self.whisper.idle_stop()
        proc.terminate.assert_called_once()

    def test_transcriber_reconfigure_forgets_the_cached_availability(self):
        hub = self.app.transcriber
        hub._availability = (time.time(), True)
        hub.reconfigure()
        self.assertEqual(hub._availability, (0.0, False))


class BackgroundLoopTests(AppCase):
    def run_loop(self, target, *args):
        stop = threading.Event()
        thread = threading.Thread(target=target, args=(stop, *args), daemon=True)
        thread.start()
        self.addCleanup(lambda: (stop.set(), thread.join(2)))
        return stop

    def wait_for(self, condition, timeout=3):
        end = time.time() + timeout
        while time.time() < end:
            if condition():
                return True
            time.sleep(0.01)
        return False

    def test_feed_loop_refreshes_when_the_sources_change(self):
        app = self.app
        app.store.channels = [{"id": "a"}]
        app.store.radios = [{"id": "r"}]
        app.store.meta["checked"] = time.time()  # fresh cache: nothing is due
        calls = []
        with (
            mock.patch("tdtlocal.feeds.TICK_SECONDS", 0.01),
            mock.patch.object(
                app.feeds, "sync", side_effect=lambda force=False: calls.append(force) or {"changed": False, "count": 1}
            ),
        ):
            self.run_loop(app.feeds.run)
            time.sleep(0.1)
            self.assertEqual(calls, [])
            app.feeds.refresh_soon()
            self.assertTrue(self.wait_for(lambda: calls))
            self.assertEqual(calls, [True])  # forced: the ETag belongs to the old source

    def test_feed_loop_reads_the_interval_every_round(self):
        app = self.app
        app.store.channels, app.store.radios = [{"id": "a"}], [{"id": "r"}]
        app.store.meta["checked"] = time.time() - 3 * 3600  # 3 h old
        calls = []
        with (
            mock.patch("tdtlocal.feeds.TICK_SECONDS", 0.01),
            mock.patch.object(
                app.feeds, "sync", side_effect=lambda force=False: calls.append(force) or {"changed": False, "count": 1}
            ),
        ):
            app.config.update_hours = 6
            self.run_loop(app.feeds.run)
            time.sleep(0.1)
            self.assertEqual(calls, [])
            app.config.update_hours = 1  # now it is overdue
            self.assertTrue(self.wait_for(lambda: calls))

    def test_feed_loop_downloads_at_once_without_a_cache_and_calls_back(self):
        app = self.app
        done = []
        with (
            mock.patch("tdtlocal.feeds.TICK_SECONDS", 0.01),
            mock.patch.object(app.feeds, "sync", return_value={"changed": True, "count": 3}) as sync,
        ):
            self.run_loop(app.feeds.run, lambda: done.append(1))
            self.assertTrue(self.wait_for(lambda: done))
        sync.assert_called()

    def test_guide_loop_is_idle_while_disabled_and_wakes_up_when_enabled(self):
        app = self.app
        app.config.epg_enabled = False
        calls = []
        result = {"changed": False, "channels": 0, "error": None}
        with (
            mock.patch("tdtlocal.epg.TICK_SECONDS", 0.01),
            mock.patch.object(app.epg, "sync", side_effect=lambda force=False: calls.append(force) or result),
        ):
            self.run_loop(app.epg.run)
            time.sleep(0.1)
            self.assertEqual(calls, [])
            app.config.epg_enabled = True
            app.epg.refresh_soon()
            self.assertTrue(self.wait_for(lambda: calls))

    def test_auto_check_is_read_when_a_sync_finishes(self):
        with mock.patch.object(self.app.health, "start") as start:
            self.app._after_sync()
            start.assert_not_called()
            self.app.config.auto_check = True
            self.app._after_sync()
            start.assert_called_once()


class SettingsApiTests(ServerCase):
    def test_get_returns_the_snapshot(self):
        status, data = self.get_json("/api/settings")
        self.assertEqual(status, 200)
        self.assertEqual(data["values"]["llm_max_tokens"], 700)
        self.assertEqual(data["locked"], ["models_dir"])  # the test harness picks its own folder

    def test_save_validates_applies_and_returns_the_new_state(self):
        with mock.patch.object(self.app, "apply_settings") as apply:
            status, data = self.post_json("/api/settings", {"llm_model": "qwen", "whisper_lang": "en"})
        self.assertEqual((status, data["ok"], sorted(data["changed"])), (200, True, ["llm_model", "whisper_lang"]))
        self.assertEqual(data["settings"]["values"]["llm_model"], "qwen")
        apply.assert_called_once()
        self.assertEqual(self.app.config.whisper_lang, "en")
        self.assertTrue((self.app.config.data_dir / "settings.json").exists())

    def test_save_reports_errors_per_field_and_changes_nothing(self):
        status, data = self.post_json("/api/settings", {"llm_url": "nope", "llm_max_tokens": 2, "llm_model": "ok"})
        self.assertEqual(status, 400)
        self.assertEqual(set(data["errors"]), {"llm_url", "llm_max_tokens"})
        self.assertEqual(self.app.config.llm_model, "")

    def test_reset(self):
        self.post_json("/api/settings", {"llm_model": "x", "update_hours": 3.0})
        status, data = self.post_json("/api/settings/reset", {"section": "ai"})
        self.assertEqual((status, data["changed"]), (200, ["llm_model"]))
        self.assertEqual(self.app.config.update_hours, 3.0)

    def test_changes_are_refused_from_other_machines(self):
        with mock.patch("tdtlocal.settings_routes._from_this_machine", return_value=False):
            for path in (
                "/api/settings",
                "/api/settings/reset",
                "/api/settings/test/ai",
                "/api/settings/test/stt",
                "/api/whisper/download",
                "/api/whisper/download/cancel",
            ):
                status, _ = self.post_json(path, {"llm_model": "x", "name": "tiny"})
                self.assertEqual(status, 403, msg=path)
        self.assertEqual(self.app.config.llm_model, "")
        # reading is allowed
        with mock.patch("tdtlocal.settings_routes._from_this_machine", return_value=False):
            self.assertEqual(self.get_json("/api/settings")[0], 200)

    def test_settings_routes_keep_the_request_guard(self):
        status, _ = self.post_json("/api/settings", {"llm_model": "x"}, headers={"Origin": "http://evil.example"})
        self.assertEqual(status, 403)
        status, _ = self.post_json("/api/settings", {"llm_model": "x"}, headers={"Sec-Fetch-Site": "cross-site"})
        self.assertEqual(status, 403)
        self.assertEqual(self.app.config.llm_model, "")

    def test_locked_settings_cannot_be_changed_through_the_api(self):
        self.app.config.locked = frozenset({"llm_url"})
        status, data = self.post_json("/api/settings", {"llm_url": "http://other/v1"})
        self.assertEqual((status, list(data["errors"])), (400, ["llm_url"]))

    def test_test_ai_lists_models_with_unsaved_values(self):
        self.origin.routes["/v1/models"] = (200, {}, b'{"data": [{"id": "qwen"}]}')
        status, data = self.post_json("/api/settings/test/ai", {"url": self.origin.url("/v1"), "api_key": "k"})
        self.assertEqual((status, data), (200, {"ok": True, "models": ["qwen"]}))
        self.assertEqual(self.origin.requests[-1][1]["authorization"], "Bearer k")

    def test_test_ai_explains_failures(self):
        self.origin.routes["/v1/models"] = (401, {}, b"no")
        _, data = self.post_json("/api/settings/test/ai", {"url": self.origin.url("/v1")})
        self.assertFalse(data["ok"])
        self.assertIn("clave de API", data["error"])
        self.origin.routes["/v1/models"] = (200, {}, b"not json")
        self.assertFalse(self.post_json("/api/settings/test/ai", {"url": self.origin.url("/v1")})[1]["ok"])
        with mock.patch("tdtlocal.ai.LOCAL_OPENER.open", side_effect=urllib.error.URLError("refused")):
            _, data = self.post_json("/api/settings/test/ai", {"url": "http://127.0.0.1:9/v1"})
        self.assertIn("no responde", data["error"])
        _, data = self.post_json("/api/settings/test/ai", {"url": "ftp://nope"})
        self.assertFalse(data["ok"])

    def test_test_stt_reports_what_it_finds_using_unsaved_values(self):
        binary = self.tmp / "ws"
        binary.write_bytes(b"b")
        model = self.tmp / "ggml-a.bin"
        model.write_bytes(b"12345")
        with mock.patch("tdtlocal.stt.Whisper.is_up", return_value=False):
            _, data = self.post_json(
                "/api/settings/test/stt", {"whisper_bin": str(binary), "whisper_model": str(model)}
            )
        self.assertTrue(data["ok"])
        self.assertEqual((data["binary"]["found"], data["model"]["found"], data["model"]["bytes"]), (True, True, 5))
        self.assertTrue(data["can_launch"])
        self.assertFalse(data["server_up"])
        _, data = self.post_json("/api/settings/test/stt", {"whisper_bin": str(self.tmp / "missing")})
        self.assertFalse(data["binary"]["found"])
        self.assertFalse(data["can_launch"])
        _, data = self.post_json("/api/settings/test/stt", {"whisper_url": "javascript:1"})
        self.assertFalse(data["ok"])


class ModelDownloadTests(ServerCase):
    NAME = "tiny-q5_1"
    FILE = "ggml-tiny-q5_1.bin"

    def setUp(self):
        super().setUp()
        self.payload = os.urandom(3_000_000)
        self.sha = hashlib.sha256(self.payload).hexdigest()
        self.models = self.app.config.models_dir
        self.release = threading.Event()
        self.release.set()

        def serve(handler):
            self.release.wait(5)
            return 200, {}, self.payload

        self.origin.routes["/tree"] = lambda h: (
            200,
            {},
            json.dumps(
                [{"path": "other.bin"}, {"path": self.FILE, "lfs": {"oid": self.sha, "size": len(self.payload)}}]
            ).encode(),
        )
        self.origin.routes["/resolve/" + self.FILE] = serve
        patcher = mock.patch.multiple(
            whisper_models, BASE_URL=self.origin.url("/resolve/"), TREE_URL=self.origin.url("/tree")
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def finish(self, timeout=10):
        self.app.models.wait(timeout)
        return self.app.models.status()

    def test_catalogue_and_installed_models(self):
        _, data = self.get_json("/api/whisper/models")
        self.assertEqual(data["installed"], [])
        names = {m["name"]: m for m in data["catalog"]}
        self.assertEqual(names["large-v3-turbo-q5_0"]["file"], "ggml-large-v3-turbo-q5_0.bin")
        self.assertFalse(any(m["installed"] for m in data["catalog"]))
        self.assertEqual(data["models_dir"], str(self.models))
        self.models.mkdir()
        (self.models / "ggml-tiny-q5_1.bin").write_bytes(b"12")
        (self.models / "notes.txt").write_bytes(b"x")
        _, data = self.get_json("/api/whisper/models")
        self.assertEqual([m["file"] for m in data["installed"]], ["ggml-tiny-q5_1.bin"])
        self.assertTrue({m["name"]: m for m in data["catalog"]}["tiny-q5_1"]["installed"])

    def test_download_verifies_and_installs(self):
        status, data = self.post_json("/api/whisper/download", {"name": self.NAME})
        self.assertEqual((status, data["ok"]), (200, True))
        result = self.finish()
        self.assertEqual((result["state"], result["verified"], result["done"]), ("done", True, len(self.payload)))
        self.assertEqual((self.models / self.FILE).read_bytes(), self.payload)
        self.assertFalse((self.models / (self.FILE + ".part")).exists())
        _, polled = self.get_json("/api/whisper/download")
        self.assertEqual(polled["state"], "done")

    def test_a_wrong_checksum_discards_the_file(self):
        self.payload = self.payload[:-1] + bytes([self.payload[-1] ^ 1])  # the published hash is for the original
        self.origin.routes["/resolve/" + self.FILE] = (200, {}, self.payload)
        self.post_json("/api/whisper/download", {"name": self.NAME})
        result = self.finish()
        self.assertEqual(result["state"], "error")
        self.assertIn("SHA-256", result["error"])
        self.assertFalse((self.models / self.FILE).exists())
        self.assertFalse((self.models / (self.FILE + ".part")).exists())

    def test_without_published_metadata_it_still_downloads_but_says_unverified(self):
        self.origin.routes["/tree"] = (500, {}, b"down")
        self.post_json("/api/whisper/download", {"name": self.NAME})
        result = self.finish()
        self.assertEqual((result["state"], result["verified"]), ("done", False))

    def test_http_errors_are_reported(self):
        self.origin.routes["/resolve/" + self.FILE] = (404, {}, b"missing")
        self.post_json("/api/whisper/download", {"name": self.NAME})
        result = self.finish()
        self.assertEqual(result["state"], "error")
        self.assertIn("404", result["error"])
        self.assertFalse((self.models / self.FILE).exists())

    def test_only_catalogue_models_can_be_requested(self):
        for name in ("../../etc/passwd", "ggml-tiny-q5_1.bin", "", "http://evil/x"):
            status, data = self.post_json("/api/whisper/download", {"name": name})
            self.assertEqual((status, data["ok"]), (400, False), msg=name)
        self.assertEqual(self.app.models.status()["state"], "idle")

    def test_one_download_at_a_time(self):
        self.release.clear()
        self.assertEqual(self.post_json("/api/whisper/download", {"name": self.NAME})[0], 200)
        status, data = self.post_json("/api/whisper/download", {"name": "base-q5_1"})
        self.assertEqual((status, data["ok"]), (409, False))
        self.assertEqual(data["download"]["name"], self.NAME)
        self.release.set()
        self.assertEqual(self.finish()["state"], "done")

    def test_a_running_download_can_be_cancelled(self):
        self.release.clear()
        self.post_json("/api/whisper/download", {"name": self.NAME})
        self.assertEqual(self.post_json("/api/whisper/download/cancel")[0], 200)
        self.release.set()
        self.assertEqual(self.finish()["state"], "cancelled")
        self.assertFalse((self.models / self.FILE).exists())
        self.assertFalse((self.models / (self.FILE + ".part")).exists())

    def test_not_enough_disk_space(self):
        free = mock.Mock(free=1000)
        with mock.patch.object(whisper_models.shutil, "disk_usage", return_value=free):
            self.post_json("/api/whisper/download", {"name": self.NAME})
            result = self.finish()
        self.assertEqual(result["state"], "error")
        self.assertIn("espacio", result["error"])

    def test_a_truncated_download_is_rejected(self):
        self.origin.routes["/resolve/" + self.FILE] = lambda h: (
            200,
            {"Content-Length": str(len(self.payload) + 10)},
            self.payload,
        )
        self.origin.routes["/tree"] = (500, {}, b"")
        self.post_json("/api/whisper/download", {"name": self.NAME})
        result = self.finish()
        self.assertEqual(result["state"], "error")


class SettingsEndToEndTests(unittest.TestCase):
    """The real command: a saved setting is used after a restart, and a flag overrides it."""

    def test_saved_settings_persist_and_flags_win(self):
        import tempfile

        from .helpers import NO_PROXY, ServerProcess

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)

        def session(*extra, change=None):
            server = ServerProcess(
                self,
                tmp.name,
                "--no-epg",
                "--source",
                "http://127.0.0.1:9/x",
                "--radio-source",
                "http://127.0.0.1:9/y",
                *extra,
            )
            snap = server.get_json_when("/api/settings")
            if change:
                request = urllib.request.Request(
                    server.base + "/api/settings",
                    data=json.dumps(change).encode(),
                    method="POST",
                    headers={"Content-Type": "application/json"},
                )
                with NO_PROXY.open(request, timeout=5) as r:
                    snap = json.loads(r.read())["settings"]
            server.proc.terminate()
            server.proc.wait(10)
            return snap

        first = session(change={"llm_model": "saved-model", "whisper_lang": "en"})
        self.assertEqual(first["values"]["llm_model"], "saved-model")
        second = session()
        self.assertEqual((second["values"]["llm_model"], second["values"]["whisper_lang"]), ("saved-model", "en"))
        third = session("--llm-model", "from-flag")
        self.assertEqual(third["values"]["llm_model"], "from-flag")
        self.assertIn("llm_model", third["locked"])
        self.assertEqual(third["values"]["whisper_lang"], "en")  # the other saved values still apply


if __name__ == "__main__":
    unittest.main()


class FormSchemaTests(unittest.TestCase):
    """The dialog (JavaScript) and the server must agree on every setting: name, section and kind."""

    KIND_TO_INPUT: ClassVar[dict[str, str]] = {
        "bool": "bool",
        "int": "number",
        "float": "number",
        "url": "url",
        "path": "path",
        "choice": "select",
        "json": "json",
    }

    def js_fields(self):
        import re
        from pathlib import Path

        from tdtlocal.config import PACKAGE_DIR

        text = (Path(PACKAGE_DIR) / "static" / "js" / "lib" / "settings-form.js").read_text(encoding="utf-8")
        block = text[text.index("export const FIELDS") : text.index("export const fieldsOf")]
        return {m[0]: (m[1], m[2]) for m in re.findall(r"name: '(\w+)', tab: '(\w+)', type: '(\w+)'", block)}

    def test_the_dialog_shows_exactly_the_server_settings(self):
        js = self.js_fields()
        self.assertEqual(set(js), {f.name for f in FIELDS})

    def test_sections_and_input_types_match(self):
        js = self.js_fields()
        for f in FIELDS:
            tab, kind = js[f.name]
            self.assertEqual(tab, f.section, msg=f.name)
            expected = "secret" if f.secret else "text" if f.kind == "text" else self.KIND_TO_INPUT[f.kind]
            self.assertEqual(kind, expected, msg=f.name)

    def test_language_choices_match(self):
        import re
        from pathlib import Path

        from tdtlocal.config import PACKAGE_DIR

        text = (Path(PACKAGE_DIR) / "static" / "js" / "lib" / "settings-form.js").read_text(encoding="utf-8")
        block = text[text.index("export const LANGUAGES") : text.index("/**\n * Fields")]
        self.assertEqual(set(re.findall(r"\b(\w{2,4}): '", block)), set(settings_module.LANGUAGES))
