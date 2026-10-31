"""Rewriting of HLS playlists so every segment and key goes back through the local proxy."""

from __future__ import annotations

import re
import urllib.parse
from collections.abc import Callable

URI_ATTR = re.compile(r'URI="([^"]*)"')


def proxy_url(absolute_url: str, channel_tag: str = "", session_tag: str = "") -> str:
    """Local ``/proxy`` URL for ``absolute_url``; non-http(s) URLs (``data:``...) are left alone.

    ``c`` carries the custom channel id (its Origin/Referer travel with playlists and segments) and
    ``s`` the playback session, to which transcription attaches only if the browser enabled it.
    """
    if not absolute_url.lower().startswith(("http://", "https://")):
        return absolute_url
    url = "/proxy?u=" + urllib.parse.quote(absolute_url, safe="")
    if channel_tag:
        url += "&c=" + urllib.parse.quote(channel_tag, safe="")
    if session_tag:
        url += "&s=" + urllib.parse.quote(session_tag, safe="")
    return url


def rewrite_playlist(
    text: str, base: str, channel_tag: str = "", session_tag: str = "", on_url: Callable[[str], None] | None = None
) -> str:
    """Point every URI in an m3u8 playlist at the proxy.

    ``on_url`` is called with each absolute http(s) URL found, so the caller can allow-list its host.
    """

    def convert(reference: str) -> str:
        absolute = urllib.parse.urljoin(base, reference)
        if on_url and absolute.lower().startswith(("http://", "https://")):
            on_url(absolute)
        return proxy_url(absolute, channel_tag, session_tag)

    out = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            out.append(line)
        elif stripped.startswith("#"):
            out.append(URI_ATTR.sub(lambda m: f'URI="{convert(m.group(1))}"', line))
        else:
            out.append(convert(stripped))
    return "\n".join(out) + "\n"
