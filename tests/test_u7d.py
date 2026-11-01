"""U7D (last 7 days): RTVE's listing is parsed newest first and each programme resolves to a clear HLS."""

from __future__ import annotations

import io
import json
import unittest
from urllib.parse import quote

from tdtlocal import u7d

from .helpers import AppCase, ServerCase

NOW = 1_793_550_000  # 2026-11-01 15:00 UTC


class FakeResponse(io.BytesIO):
    """What ``Net.open`` returns, with the URL it ended on."""

    def __init__(self, body: bytes, url: str) -> None:
        super().__init__(body)
        self._url = url

    def geturl(self) -> str:
        return self._url


class FakeNet:
    """Answers by URL fragment (a body, or ``(body, final_url)``), records the requests, never touches the network."""

    def __init__(self, answers: dict[str, bytes | tuple[bytes, str]]) -> None:
        self.answers = answers
        self.calls: list[tuple[str, dict[str, str]]] = []

    def open(self, url, headers=None, require_allowed=True, timeout=20):
        self.calls.append((url, dict(headers or {})))
        for fragment, answer in self.answers.items():
            if fragment in url:
                body, final = answer if isinstance(answer, tuple) else (answer, url)
                return FakeResponse(body, final)
        raise AssertionError(f"unexpected request: {url}")


SCHEDULE = json.dumps(
    {
        "items": [
            {"idAsset": 1, "name": "Telediario 1", "episode_name": None, "begintime": "20261101145500"},
            {"idAsset": 2, "name": "Cine", "episode_name": "Parte 2", "begintime": "20261031220000"},
            {"name": "Sin asset", "begintime": "20261101120000"},
            {"idAsset": 3, "name": "Mañana", "begintime": "20991231120000"},
        ]
    }
).encode()


class ParseTests(unittest.TestCase):
    def test_rtve_keeps_assets_and_drops_the_none_episode(self) -> None:
        items = u7d.parse_rtve(
            {
                "items": [
                    {"idAsset": "1", "name": "Noticias", "episode_name": "None", "begintime": "20261101120000"},
                    {"name": "Sin asset", "begintime": "20261101120000"},
                    {"idAsset": "2", "original_event_name": "Cine", "episode_name": "Parte 2", "begintime": "bad"},
                    {"idAsset": "../x", "name": "Raro"},
                ]
            }
        )
        self.assertEqual([i["id"] for i in items], ["1", "2"])
        self.assertEqual(items[0]["subtitle"], "")
        self.assertEqual(items[1]["title"], "Cine")
        self.assertEqual(items[1]["subtitle"], "Parte 2")
        self.assertEqual(items[1]["ts"], 0)
        self.assertGreater(items[0]["ts"], 1_700_000_000)
        self.assertEqual(items[0]["image"], "https://img.rtve.es/v/1/?w=320")

    def test_rtve_time_is_madrid_time(self) -> None:
        # 2026-11-01 14:55 in Madrid (winter time, UTC+1) is 13:55 UTC; without a time zone database it is read as UTC
        self.assertIn(u7d._rtve_ts("20261101145500"), (1_793_541_300, 1_793_544_900))
        self.assertEqual(u7d._rtve_ts(""), 0)
        self.assertEqual(u7d._rtve_ts("20261301000000"), 0)  # month 13

    def test_newest_first_drops_duplicates_and_the_future(self) -> None:
        def item(ref: str, ts: int) -> dict:
            return {"id": ref, "title": ref, "subtitle": "", "ts": ts}

        out = u7d._newest_first([item("a", 10), item("b", 30), item("a", 20), item("c", NOW + 3600), item("", 5)], NOW)
        self.assertEqual([i["id"] for i in out], ["b", "a"])
        self.assertEqual(out[1]["ts"], 20)  # the newest copy of a duplicate wins


class ChannelListTests(unittest.TestCase):
    def test_channels_reuse_the_logo_of_their_live_channel(self) -> None:
        live = [{"id": "la-1", "logo": "L1"}, {"id": "antena3", "logo": "L3"}]
        out = {c["id"]: c for c in u7d.channels(live)}
        self.assertEqual(out["u7d-la-1"]["logo"], "L1")
        self.assertEqual(out["u7d-la-1"]["kind"], "u7d")
        self.assertEqual(out["u7d-la-1"]["sources"], ["u7d:la-1"])
        self.assertEqual(out["u7d-clan"]["logo"], "")
        self.assertTrue(u7d.is_u7d(out["u7d-clan"]["sources"][0]))
        self.assertFalse(u7d.is_u7d("https://x/a.m3u8"))
        self.assertEqual(list(out), ["u7d-la-1", "u7d-la-2", "u7d-24h", "u7d-teledeporte", "u7d-clan"])

    def test_every_channel_has_a_provider_that_can_list_and_resolve(self) -> None:
        for chan in u7d.CHANNELS.values():
            self.assertIn(chan.provider, u7d.LISTERS)
            self.assertIn(chan.provider, u7d.RESOLVERS)


class ProgrammesTests(unittest.TestCase):
    def test_sorted_newest_first_without_the_future_and_cached(self) -> None:
        net = FakeNet({"schedule/tv1.json": SCHEDULE})
        guide = u7d.U7d(net)
        out = guide.programmes("la-1", now=NOW)
        self.assertEqual([i["id"] for i in out], ["1", "2"])
        self.assertEqual(net.calls[0][1], {"Accept": "application/json"})  # no Origin, no Referer: nothing imitated
        guide.programmes("la-1", now=NOW + 60)
        self.assertEqual(len(net.calls), 1)  # inside the cache window
        guide.programmes("la-1", now=NOW + u7d.CACHE_SECONDS + 1)
        self.assertEqual(len(net.calls), 2)

    def test_thumbnails_are_handed_to_the_logo_proxy(self) -> None:
        allowed: list[str] = []
        guide = u7d.U7d(FakeNet({"schedule/": SCHEDULE}), allowed.append)
        out = guide.programmes("la-2", now=NOW)
        self.assertEqual(allowed, ["https://img.rtve.es/v/1/?w=320", "https://img.rtve.es/v/2/?w=320"])
        self.assertEqual(out[0]["image"], allowed[0])

    def test_unknown_channel(self) -> None:
        with self.assertRaises(ValueError):
            u7d.U7d(FakeNet({})).programmes("nope")

    def test_a_listing_that_is_not_an_object_is_empty(self) -> None:
        self.assertEqual(u7d.U7d(FakeNet({"schedule/": b"[1, 2]"})).programmes("la-1", now=NOW), [])


class ResolveTests(unittest.TestCase):
    def test_a_clear_programme_returns_the_final_url(self) -> None:
        net = FakeNet(
            {
                "ztnr.rtve.es/ztnr/17281881.m3u8": (
                    b"#EXTM3U\n#EXT-X-STREAM-INF\nv.m3u8\n",
                    "https://cdn/real/master.m3u8",
                )
            }
        )
        self.assertEqual(u7d.resolve(net, "la-1", "17281881"), {"url": "https://cdn/real/master.m3u8"})
        self.assertEqual(net.calls[0][1], {})  # the application's own headers, nothing added

    def test_a_programme_with_drm_is_refused_with_a_clear_message(self) -> None:
        net = FakeNet({"ztnr.rtve.es": (b"#EXTM3U\n#EXT-X-KEY:URI=skd://hls_drm\n", "https://cdn/drm.m3u8")})
        with self.assertRaisesRegex(RuntimeError, "DRM"):
            u7d.resolve(net, "la-2", "1")

    def test_something_that_is_not_a_playlist_is_refused(self) -> None:
        net = FakeNet({"ztnr.rtve.es": (b"<html>no</html>", "https://cdn/x")})
        with self.assertRaisesRegex(RuntimeError, "HLS"):
            u7d.resolve(net, "la-1", "1")

    def test_a_bad_channel_or_reference(self) -> None:
        for key, ref in (("nope", "1"), ("la-1", "../../x"), ("la-1", ""), ("la-1", "a" * 200), ("la-1", "a/b")):
            with self.assertRaises(ValueError):
                u7d.resolve(FakeNet({}), key, ref)


class StoreTests(AppCase):
    def test_the_u7d_channels_are_listed_only_with_a_list_and_are_never_checked(self) -> None:
        self.assertEqual([c for c in self.app.store.all_channels() if c["kind"] == "u7d"], [])
        self.app.store.channels = [
            {
                "id": "la-1",
                "name": "La 1",
                "kind": "tv",
                "category": "Nacionales",
                "group": "",
                "sources": ["https://x/a.m3u8"],
                "fmts": ["hls"],
                "web": "",
                "logo": "",
                "epg": "",
                "tags": [],
            }
        ]
        listed = [c for c in self.app.store.all_channels() if c["kind"] == "u7d"]
        self.assertEqual(len(listed), len(u7d.CHANNELS))
        payload = self.app.channels_payload()["channels"]
        mine = next(c for c in payload if c["id"] == "u7d-la-1")
        self.assertIsNone(mine["ok"])
        self.assertIsNone(mine["sources"][0]["ok"])
        self.assertNotIn("u7d:la-1", self.app.store.sources("all"))  # the health check never gets them


class ServerTests(ServerCase):
    def test_play_resolves_and_allows_the_host_for_the_proxy(self) -> None:
        self.origin.routes["/ztnr/55.m3u8"] = (200, {}, b"#EXTM3U\n")
        from unittest import mock

        with mock.patch.object(u7d, "RTVE_RESOLVER", self.origin.url("/ztnr/{asset}.m3u8")):
            status, data = self.get_json("/api/u7d/play?c=la-1&r=55")
        self.assertEqual(status, 200)
        self.assertEqual(data["url"], self.origin.url("/ztnr/55.m3u8"))

    def test_bad_requests_are_404_and_provider_failures_are_502(self) -> None:
        self.assertEqual(self.get_json("/api/u7d?c=nope")[0], 404)
        self.assertEqual(self.get_json("/api/u7d/play?c=la-1&r=" + quote("../x"))[0], 404)
        from unittest import mock

        with mock.patch.object(u7d, "RTVE_RESOLVER", self.origin.url("/missing/{asset}.m3u8")):
            status, data = self.get_json("/api/u7d/play?c=la-1&r=1")
        self.assertEqual(status, 502)
        self.assertIn("U7D", data["error"])

    def test_programme_covers_may_be_bigger_than_logos_but_not_huge(self) -> None:
        png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
        self.origin.routes["/cover.png"] = (200, {}, png + b"x" * 2_000_000)
        self.origin.routes["/huge.png"] = (200, {}, png + b"x" * 3_100_000)
        for name in ("cover", "huge"):
            self.app.store.cover_urls.add(self.origin.url(f"/{name}.png"))
        self.assertEqual(self.request("GET", "/logo?u=" + quote(self.origin.url("/cover.png"), safe=""))[0], 200)
        self.assertEqual(self.request("GET", "/logo?u=" + quote(self.origin.url("/huge.png"), safe=""))[0], 404)


class CoverTests(ServerCase):
    GOOD = "https://imagenes.atresplayer.com/atp/clipping/x/386x217.jpg?optimize=low"

    def test_only_https_covers_of_atresplayers_image_server_are_accepted(self) -> None:
        self.assertTrue(u7d.cover_ok(self.GOOD))
        for bad in (
            "http://imagenes.atresplayer.com/x.jpg",
            "https://imagenes.atresplayer.com.evil.example/x.jpg",
            "https://evil.example/imagenes.atresplayer.com/x.jpg",
            "https://user@imagenes.atresplayer.com/x.jpg",
            "https://imagenes.atresplayer.com:8443/x.jpg",
            "https://127.0.0.1/x.jpg",
            "https://imagenes.atresplayer.com/" + "x" * 500,
            "",
            None,
            5,
        ):
            self.assertFalse(u7d.cover_ok(bad), bad)

    def test_the_page_can_hand_over_covers_and_the_proxy_then_serves_them(self) -> None:
        status, data = self.post_json("/api/u7d/covers", {"urls": [self.GOOD, "https://evil.example/x.jpg", 7]})
        self.assertEqual((status, data), (200, {"ok": True, "taken": 1}))
        self.assertEqual(self.app.store.cover_urls, {self.GOOD})
        self.assertEqual(self.post_json("/api/u7d/covers", {"urls": "nope"})[1]["taken"], 0)
        self.assertEqual(self.post_json("/api/u7d/covers", {})[1]["taken"], 0)

    def test_at_most_a_bounded_number_of_covers_is_taken_at_once(self) -> None:
        urls = [f"https://imagenes.atresplayer.com/{i}.jpg" for i in range(u7d.MAX_COVERS + 50)]
        self.assertEqual(self.post_json("/api/u7d/covers", {"urls": urls})[1]["taken"], u7d.MAX_COVERS)


if __name__ == "__main__":
    unittest.main()
