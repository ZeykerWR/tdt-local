import json
import struct
import time
import unittest
import urllib.error
from typing import ClassVar
from unittest import mock

from tdtlocal.ai import ModelError, parse_reply, sanitize_reply
from tdtlocal.stt import keep_segment, multipart, rms, wav_from_pcm

from .helpers import AppCase

NOW = time.mktime((2099, 1, 1, 20, 30, 0, 0, 1, -1))  # local time, so the "HH:MM" in prompts is predictable


def chat_reply(content, finish="stop"):
    return {"choices": [{"message": {"content": content}, "finish_reason": finish}]}


class ReplyParsingTests(unittest.TestCase):
    valid: ClassVar[dict[str, str]] = {"la-1": "La 1", "la-2": "La 2", "trece": "TRECE"}

    def test_parse_plain_json(self):
        self.assertEqual(parse_reply('{"say": "hola"}'), {"say": "hola"})

    def test_parse_json_surrounded_by_text(self):
        self.assertEqual(parse_reply('Claro:\n{"say": "hola"}\nSaludos')["say"], "hola")

    def test_parse_garbage_falls_back_to_plain_message(self):
        self.assertEqual(parse_reply("no hay json")["say"], "no hay json")
        self.assertEqual(parse_reply("{roto")["actions"], [])
        self.assertEqual(parse_reply("[1, 2]")["actions"], [])

    def test_unknown_ids_and_actions_are_dropped(self):
        reply = sanitize_reply(
            {
                "say": "ok",
                "actions": [
                    {"do": "play", "id": "la-1"},
                    {"do": "play", "id": "inventado"},
                    {"do": "explota"},
                    "texto",
                ],
                "results": [{"id": "la-2", "why": "porque sí"}, {"id": "nope", "why": "x"}, "x"],
            },
            self.valid,
        )
        self.assertEqual(reply["actions"], [{"do": "play", "id": "la-1"}])
        self.assertEqual(reply["results"], [{"id": "la-2", "why": "porque sí"}])

    def test_kind_and_guide_actions_are_validated(self):
        reply = sanitize_reply(
            {
                "actions": [
                    {"do": "kind", "kind": "radio"},
                    {"do": "kind", "kind": "otra"},
                    {"do": "guide"},
                    {"do": "kind"},
                ]
            },
            {},
        )
        self.assertEqual(reply["actions"], [{"do": "kind", "kind": "radio"}, {"do": "guide"}])

    def test_at_most_four_actions_are_considered(self):
        reply = sanitize_reply({"actions": [{"do": "guide"}] * 9}, {})
        self.assertEqual(len(reply["actions"]), 4)

    def test_multi_keeps_valid_ids_max_four_and_validates_rotation(self):
        valid = {str(i): str(i) for i in range(10)}
        reply = sanitize_reply(
            {
                "actions": [
                    {"do": "multi", "ids": ["0", "x", "1", "2", "3", "4", "5"], "rotate": 30},
                    {"do": "multi", "ids": ["1"], "rotate": 1},
                    {"do": "multi", "ids": ["1"], "rotate": True},
                    {"do": "multi", "ids": ["1"], "rotate": "30"},
                    {"do": "multi", "ids": ["zzz"]},
                ]
            },
            valid,
        )
        self.assertEqual(reply["actions"][0], {"do": "multi", "ids": ["0", "1", "2", "3"], "rotate": 30})
        self.assertEqual([a["rotate"] for a in reply["actions"][1:]], [None, None, None])
        self.assertEqual(len(reply["actions"]), 4)

    def test_lengths_are_capped(self):
        reply = sanitize_reply({"say": "x" * 900, "results": [{"id": "la-1", "why": "y" * 900}] * 9}, self.valid)
        self.assertEqual(len(reply["say"]), 500)
        self.assertEqual(len(reply["results"]), 6)
        self.assertEqual(len(reply["results"][0]["why"]), 200)


class AssistantTests(AppCase):
    def setUp(self):
        super().setUp()
        self.app = self.make_app(llm_url=self.origin.url("/v1"), llm_model="modelo-x")
        store = self.app.store
        guide_start = NOW - 1800
        store.channels = [
            {
                "id": "la-1",
                "name": "La 1",
                "kind": "tv",
                "category": "Nacionales",
                "group": "",
                "epg": "La1.TV",
                "sources": ["https://s.example/1.m3u8"],
                "logo": "",
            },
            {
                "id": "la-2",
                "name": "La 2",
                "kind": "tv",
                "category": "Nacionales",
                "group": "",
                "epg": "La2.TV",
                "sources": ["https://s.example/2.m3u8"],
                "logo": "",
            },
            {
                "id": "trece",
                "name": "TRECE",
                "kind": "tv",
                "category": "Nacionales",
                "group": "",
                "epg": "",
                "sources": ["https://s.example/13.m3u8"],
                "logo": "",
            },
            {
                "id": "caido",
                "name": "Caído",
                "kind": "tv",
                "category": "Nacionales",
                "group": "",
                "epg": "",
                "sources": ["https://s.example/down.m3u8"],
                "logo": "",
            },
            {
                "id": "sin-directo",
                "name": "Sin directo",
                "kind": "tv",
                "category": "Nacionales",
                "group": "",
                "epg": "",
                "sources": [],
                "logo": "",
            },
        ]
        store.radios = [
            {
                "id": "radio-uno",
                "name": "Radio Uno",
                "kind": "radio",
                "category": "Nacionales",
                "group": "",
                "epg": "",
                "sources": ["https://r.example/1.mp3"],
                "logo": "",
            }
        ]
        store.status = {"https://s.example/down.m3u8": {"ok": False}}
        store.epg["tv"] = {
            "La1.TV": [
                [guide_start, NOW + 1800, "Telediario", "noticias del día", "Noticias"],
                [NOW + 1800, NOW + 5400, "El tiempo", "", ""],
            ],
            "La2.TV": [[guide_start, NOW + 1800, "Partido de baloncesto", "", "Deportes"]],
        }

    def test_candidates_rank_by_programme_and_name(self):
        lines, valid = self.app.assistant.candidates("hay noticias ahora", ["tv"], now=NOW)
        self.assertEqual(lines[0].split("|")[0], "la-1")
        self.assertIn("ahora: Telediario", lines[0])
        self.assertIn("luego: El tiempo", lines[0])
        self.assertNotIn("caido", valid)  # known to be down
        self.assertNotIn("sin-directo", valid)  # nothing to play

    def test_topic_synonyms_widen_the_match(self):
        _, valid = self.app.assistant.candidates("quiero ver deporte", ["tv"], now=NOW)
        self.assertIn("la-2", valid)  # "baloncesto" belongs to the sports group

    def test_name_in_the_question_wins(self):
        lines, _ = self.app.assistant.candidates("pon trece", ["tv"], now=NOW)
        self.assertEqual(lines[0].split("|")[0], "trece")

    def test_vague_question_still_offers_channels_with_guide(self):
        _, valid = self.app.assistant.candidates("sorpréndeme", ["tv"], now=NOW)
        self.assertEqual(set(valid), {"la-1", "la-2"})

    def test_radio_pool(self):
        _, valid = self.app.assistant.candidates("radio uno", ["radio"], now=NOW)
        self.assertEqual(list(valid), ["radio-uno"])

    def test_chat_request_disables_thinking_and_uses_the_schema(self):
        self.origin.routes["/v1/chat/completions"] = lambda h: (200, {}, json.dumps(chat_reply("hola")).encode())
        self.app.assistant.chat([{"role": "user", "content": "hola"}], 100, {"type": "object"})
        body = json.loads(self._last_body)
        self.assertEqual(body["chat_template_kwargs"], {"enable_thinking": False})
        self.assertEqual(body["reasoning_effort"], "none")
        self.assertEqual(body["model"], "modelo-x")
        self.assertEqual(body["response_format"]["json_schema"]["schema"], {"type": "object"})

    def test_chat_strips_think_blocks(self):
        for content in ('<think>razonando</think>\n{"a": 1}', '<think></think>{"a": 1}', '{"a": 1}<think>sin cerrar'):
            self.origin.routes["/v1/chat/completions"] = (200, {}, json.dumps(chat_reply(content)).encode())
            self.assertEqual(self.app.assistant.chat([]), '{"a": 1}', msg=content)

    def test_chat_reports_a_model_that_only_thinks(self):
        self.origin.routes["/v1/chat/completions"] = (
            200,
            {},
            json.dumps(chat_reply("<think>sigo pensando", finish="length")).encode(),
        )
        with self.assertRaisesRegex(ModelError, "pensando"):
            self.app.assistant.chat([])

    def test_chat_rejects_malformed_responses(self):
        for body in (b"<html>", b"{}", b'{"choices": []}', b'{"choices": [{"message": null}]}', b"[1]"):
            self.origin.routes["/v1/chat/completions"] = (200, {}, body)
            with self.assertRaises(ModelError, msg=body):
                self.app.assistant.chat([])

    def test_ask_end_to_end_filters_hallucinations(self):
        reply = {
            "say": "Te pongo La 1",
            "actions": [{"do": "play", "id": "la-1"}, {"do": "play", "id": "fantasma"}],
            "results": [],
        }
        self.origin.routes["/v1/chat/completions"] = (200, {}, json.dumps(chat_reply(json.dumps(reply))).encode())
        out = self.app.assistant.ask("pon la 1", "tv", now=NOW)
        self.assertEqual(out["actions"], [{"do": "play", "id": "la-1"}])
        self.assertEqual(out["say"], "Te pongo La 1")

    def test_ask_prompt_contains_candidates_and_time(self):
        self.origin.routes["/v1/chat/completions"] = (200, {}, json.dumps(chat_reply("{}")).encode())
        self.app.assistant.ask("hay noticias", "tv", now=NOW)
        prompt = json.loads(self._last_body)["messages"][1]["content"]
        self.assertIn("la-1|La 1|ahora: Telediario", prompt)
        self.assertIn("jueves, 20:30", prompt)  # 2099-01-01 is a Thursday

    def test_ask_mentions_radio_searches_both_lists(self):
        self.origin.routes["/v1/chat/completions"] = (200, {}, json.dumps(chat_reply("{}")).encode())
        self.app.assistant.ask("pon la radio uno", "tv", now=NOW)
        self.assertIn("radio-uno", json.loads(self._last_body)["messages"][1]["content"])

    def test_empty_question(self):
        with self.assertRaises(ValueError):
            self.app.assistant.ask("   ")

    @property
    def _last_body(self):
        return self.origin.bodies[-1]


class SttHelperTests(unittest.TestCase):
    def test_wav_header(self):
        pcm = b"\x01\x00" * 100
        wav = wav_from_pcm(pcm)
        self.assertEqual(wav[:4], b"RIFF")
        self.assertEqual(struct.unpack("<I", wav[4:8])[0], 36 + len(pcm))
        self.assertEqual(wav[8:16], b"WAVEfmt ")
        channels, rate = struct.unpack("<HI", wav[22:28])
        self.assertEqual((channels, rate), (1, 16000))
        self.assertEqual(wav[36:40], b"data")
        self.assertEqual(wav[44:], pcm)

    def test_rms(self):
        self.assertEqual(rms(b"\x00\x00" * 320), 0)
        loud = struct.pack("<h", 10000) * 320
        self.assertAlmostEqual(rms(loud), 10000, delta=1)
        self.assertEqual(rms(b""), 0)

    def test_segment_filter_drops_hallucinations_and_noise(self):
        def seg(text, **extra):
            return {"text": text, **extra}

        self.assertTrue(keep_segment(seg("Buenas noches y bienvenidos")))
        for text in (
            "",
            "   ",
            "[Música]",
            "(aplausos)",
            "♪ la la ♪",
            "Subtítulos realizados por la comunidad de Amara.org",
            "Gracias por ver el vídeo",
            "Música",
            "Aplausos. Música",
            "visita www.ejemplo.com",
        ):
            self.assertFalse(keep_segment(seg(text)), msg=text)
        self.assertFalse(keep_segment(seg("hola", no_speech_prob=0.9)))
        self.assertFalse(keep_segment(seg("hola", avg_logprob=-2.0)))
        self.assertTrue(keep_segment(seg("hola", no_speech_prob=0.1, avg_logprob=-0.4)))

    def test_multipart_layout(self):
        body, boundary = multipart({"language": "es", "temperature": "0.0"}, b"WAVDATA")
        text = body.decode("latin-1")
        self.assertIn(f'--{boundary}\r\nContent-Disposition: form-data; name="language"\r\n\r\nes\r\n', text)
        self.assertIn('name="file"; filename="a.wav"', text)
        self.assertIn("WAVDATA\r\n", text)
        self.assertTrue(text.endswith(f"--{boundary}--\r\n"))


class TranscriberTests(AppCase):
    def test_sessions_and_polling(self):
        hub = self.app.transcriber
        self.assertFalse(hub.poll("s1", 0)["active"])
        hub.set_session("s1", True)
        self.addCleanup(hub.close)
        self.assertTrue(hub.is_active("s1"))
        poll = hub.poll("s1", 0)
        self.assertTrue(poll["active"])
        self.assertEqual(poll["items"], [])
        hub.set_session("s1", False)
        self.assertFalse(hub.is_active("s1"))

    def test_tap_only_exists_for_active_sessions(self):
        hub = self.app.transcriber
        self.assertIsNone(hub.tap("", "https://x/seg.ts", "video/mp2t", True, b""))
        self.assertIsNone(hub.tap("s1", "https://x/seg.ts", "video/mp2t", True, b""))
        hub.set_session("s1", True)
        self.addCleanup(hub.close)
        tap = hub.tap("s1", "https://x/seg.ts", "video/mp2t", True, b"head")
        self.assertIsNotNone(tap)
        tap.feed(b"-body")
        tap.finish()
        job = hub._queue.get_nowait()
        self.assertEqual((job["tag"], job["u"], job["data"]), ("s1", "https://x/seg.ts", b"head-body"))

    def test_full_queue_drops_the_oldest_job(self):
        hub = self.app.transcriber
        for i in range(30):
            hub.submit("s", f"u{i}", data=b"x")
        self.assertEqual(hub._queue.qsize(), 24)
        first = hub._queue.get_nowait()
        self.assertEqual(first["u"], "u6")

    def test_unavailable_without_ffmpeg_or_whisper(self):
        hub = self.app.transcriber
        hub.ffmpeg = ""
        self.assertFalse(hub.available())
        disabled = self.make_app(stt_enabled=False).transcriber
        self.assertFalse(disabled.available())

    def test_whisper_client_filters_segments(self):
        whisper = self.make_app(whisper_url=self.origin.url("")).transcriber.whisper
        segments = [
            {"start": 0.0, "end": 2.5, "text": " Buenas noches "},
            {"start": 2.5, "end": 3.0, "text": "Subtítulos por la comunidad"},
            {"start": 3.0, "end": 4.0, "text": "[Música]"},
        ]
        self.origin.routes["/"] = (200, {}, b"whisper")
        self.origin.routes["/inference"] = (200, {}, json.dumps({"segments": segments}).encode())
        self.assertEqual(whisper.transcribe(wav_from_pcm(b"\x00\x00" * 10)), [[0.0, 2.5, "Buenas noches"]])
        self.assertEqual(whisper.state, "ready")

    def test_whisper_without_server_or_binary_raises_a_clear_error(self):
        app = self.make_app(whisper_url="http://127.0.0.1:9", whisper_bin=str(self.tmp / "nope"))
        whisper = app.transcriber.whisper
        self.assertFalse(whisper.configured())
        refused = mock.patch("tdtlocal.stt.LOCAL_OPENER.open", side_effect=urllib.error.URLError("refused"))
        with refused, self.assertRaisesRegex(RuntimeError, "no hay whisper-server"):
            whisper.ensure()
        self.assertEqual(whisper.state, "error")

    def test_model_autodetection(self):
        (self.tmp / "models").mkdir()
        (self.tmp / "models" / "ggml-b.bin").write_bytes(b"")
        (self.tmp / "models" / "ggml-a.bin").write_bytes(b"")
        (self.tmp / "models" / "otro.bin").write_bytes(b"")
        self.assertTrue(self.make_app().transcriber.whisper.model.endswith("ggml-a.bin"))


if __name__ == "__main__":
    unittest.main()
