"""Detection of SCTE-35 ad-break signalling: pure functions, no network and no state.

SCTE-35 is the standard that marks where an ad break starts and ends in a video stream. In an HLS stream it
shows up as tags in the playlist (``#EXT-X-CUE-OUT``, ``#EXT-X-DATERANGE`` with ``SCTE35-OUT``...), as a data
PID of the MPEG-TS segments (``stream_type`` 0x86, ``CUEI`` registration) or as ``emsg`` boxes of fragmented MP4.
This module finds those signs and decodes the binary ``splice_info_section`` they carry.
"""

from __future__ import annotations

import base64
import binascii
import re
import urllib.parse
from typing import Any

Marker = dict[str, Any]

TS_PACKET = 188
SCTE_STREAM_TYPE = 0x86
EMSG_SCHEMES = (b"urn:scte:scte35:2013:bin", b"urn:scte:scte35:2013:xml")
MAX_RAW = 300

COMMANDS = {
    0x00: "splice_null",
    0x04: "splice_schedule",
    0x05: "splice_insert",
    0x06: "time_signal",
    0x07: "bandwidth_reservation",
    0xFF: "private_command",
}
SPLICE_INSERT = 0x05
SEGMENTATION_START = frozenset({0x22, 0x30, 0x32, 0x34, 0x36, 0x38, 0x3A})
SEGMENTATION_END = frozenset({0x23, 0x31, 0x33, 0x35, 0x37, 0x39, 0x3B})
SEGMENTATION_TYPES = {
    0x00: "no indicado",
    0x01: "identificación de contenido",
    0x10: "inicio de programa",
    0x11: "fin de programa",
    0x12: "fin anticipado de programa",
    0x13: "salida del programa",
    0x14: "reanudación del programa",
    0x20: "inicio de capítulo",
    0x21: "fin de capítulo",
    0x22: "inicio de pausa",
    0x23: "fin de pausa",
    0x30: "inicio de anuncio (proveedor)",
    0x31: "fin de anuncio (proveedor)",
    0x32: "inicio de anuncio (distribuidor)",
    0x33: "fin de anuncio (distribuidor)",
    0x34: "inicio de oportunidad publicitaria (proveedor)",
    0x35: "fin de oportunidad publicitaria (proveedor)",
    0x36: "inicio de oportunidad publicitaria (distribuidor)",
    0x37: "fin de oportunidad publicitaria (distribuidor)",
    0x38: "inicio de superposición (proveedor)",
    0x39: "fin de superposición (proveedor)",
    0x3A: "inicio de superposición (distribuidor)",
    0x3B: "fin de superposición (distribuidor)",
    0x40: "inicio de evento no programado",
    0x41: "fin de evento no programado",
    0x50: "inicio de red",
    0x51: "fin de red",
}


# ---------------------------------------------------------------- binary splice_info_section
def crc32_mpeg(data: bytes) -> int:
    """CRC-32/MPEG-2: the check of every MPEG section. It is 0 over a section that includes its own CRC."""
    crc = 0xFFFFFFFF
    for byte in data:
        crc ^= byte << 24
        for _ in range(8):
            crc = ((crc << 1) ^ 0x04C11DB7) & 0xFFFFFFFF if crc & 0x80000000 else (crc << 1) & 0xFFFFFFFF
    return crc


class _Reader:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.pos = 0

    def take(self, count: int) -> bytes:
        if count < 0 or self.pos + count > len(self.data):
            raise ValueError("datos cortados")
        chunk = self.data[self.pos : self.pos + count]
        self.pos += count
        return chunk

    def u8(self) -> int:
        return self.take(1)[0]

    def u16(self) -> int:
        return int.from_bytes(self.take(2), "big")

    def u32(self) -> int:
        return int.from_bytes(self.take(4), "big")


def _splice_time(reader: _Reader) -> float | None:
    """``splice_time()``: seconds of the presentation clock, or ``None`` if the time is not specified."""
    first = reader.u8()
    if not first & 0x80:
        return None
    return (((first & 1) << 32) | reader.u32()) / 90000


def _break_duration(reader: _Reader) -> float:
    first = reader.u8()
    return (((first & 1) << 32) | reader.u32()) / 90000


def _splice_insert(reader: _Reader) -> dict[str, Any]:
    out: dict[str, Any] = {"event_id": reader.u32()}
    out["cancel"] = bool(reader.u8() & 0x80)
    if out["cancel"]:
        return out
    flags = reader.u8()
    program, has_duration, immediate = bool(flags & 0x40), bool(flags & 0x20), bool(flags & 0x10)
    pts = None
    if program:
        if not immediate:
            pts = _splice_time(reader)
    else:
        for _ in range(reader.u8()):
            reader.u8()  # component_tag
            if not immediate:
                moment = _splice_time(reader)
                pts = moment if pts is None else pts
    out.update(out_of_network=bool(flags & 0x80), immediate=immediate, pts_s=pts)
    if has_duration:
        out["duration_s"] = _break_duration(reader)
    return out


def _printable(raw: bytes) -> str:
    return raw.decode("ascii") if raw and all(32 <= b < 127 for b in raw) else raw.hex()


def _segmentation(body: bytes) -> dict[str, Any]:
    """``segmentation_descriptor()`` without its tag, length and ``CUEI`` identifier."""
    reader = _Reader(body)
    seg: dict[str, Any] = {"event_id": reader.u32()}
    seg["cancel"] = bool(reader.u8() & 0x80)
    if seg["cancel"]:
        return seg
    flags = reader.u8()
    if not flags & 0x80:  # not program_segmentation_flag: a list of components follows
        reader.take(6 * reader.u8())
    if flags & 0x40:
        seg["duration_s"] = int.from_bytes(reader.take(5), "big") / 90000
    seg["upid_type"] = reader.u8()
    seg["upid"] = _printable(reader.take(reader.u8()))[:80]
    type_id = reader.u8()
    seg["type_id"] = type_id
    seg["type"] = SEGMENTATION_TYPES.get(type_id, f"0x{type_id:02x}")
    return seg


def _descriptors(reader: _Reader) -> list[dict[str, Any]]:
    """The segmentation descriptors of the loop; whatever cannot be read is skipped, not fatal."""
    found: list[dict[str, Any]] = []
    try:
        length = reader.u16()
        end = reader.pos + length
        while reader.pos + 2 <= min(end, len(reader.data)):
            tag, size = reader.u8(), reader.u8()
            body = reader.take(size)
            if tag == 0x02 and body[:4] == b"CUEI":
                try:
                    found.append(_segmentation(body[4:]))
                except (ValueError, IndexError):
                    found.append({"type": "descriptor ilegible"})
    except ValueError:
        pass
    return found


def decode_splice_info(data: bytes) -> dict[str, Any] | None:
    """Decode a ``splice_info_section``; ``None`` if it is not one. Fields that cannot be read are left out."""
    try:
        return _decode(data)
    except (ValueError, IndexError):
        return None


def _decode(data: bytes) -> dict[str, Any]:
    if len(data) < 17 or data[0] != 0xFC:
        raise ValueError("no es una sección splice_info")
    size = 3 + (((data[1] & 0x0F) << 8) | data[2])
    if size > len(data):
        raise ValueError("sección incompleta")
    section = data[:size]
    reader = _Reader(section)
    reader.take(3)
    reader.u8()  # protocol_version
    header = reader.take(5)
    encrypted = bool(header[0] & 0x80)
    reader.u8()  # cw_index
    lengths = reader.take(3)
    command_length = ((lengths[1] & 0x0F) << 8) | lengths[2]
    command_type = reader.u8()
    out: dict[str, Any] = {
        "command": COMMANDS.get(command_type, f"0x{command_type:02x}"),
        "command_type": command_type,
        "crc_ok": crc32_mpeg(section) == 0,
        "encrypted": encrypted,
    }
    if encrypted:
        return out  # the rest cannot be read without the key
    body_start = reader.pos
    if command_type == SPLICE_INSERT:
        out.update(_splice_insert(reader))
    elif command_type == 0x06:
        out["pts_s"] = _splice_time(reader)
    if command_length != 0xFFF:  # 0xFFF = "not specified": trust what was parsed
        reader.pos = body_start + command_length
    segmentation = _descriptors(reader)
    if segmentation:
        out["segmentation"] = segmentation
    return out


def splice_kind(info: dict[str, Any]) -> str:
    """``cue-out`` (an ad break starts), ``cue-in`` (it ends) or the generic ``scte35``."""
    if info.get("command_type") == SPLICE_INSERT and not info.get("cancel"):
        return "cue-out" if info.get("out_of_network") else "cue-in"
    for seg in info.get("segmentation", []):
        if seg.get("type_id") in SEGMENTATION_START:
            return "cue-out"
        if seg.get("type_id") in SEGMENTATION_END:
            return "cue-in"
    return "scte35"


def _seconds(value: float) -> str:
    return f"{value:g} s"


def splice_summary(info: dict[str, Any]) -> str:
    """One line for people: what the decoded message says."""
    parts = [str(info.get("command", "scte35"))]
    if info.get("command_type") == SPLICE_INSERT:
        if info.get("cancel"):
            parts.append("cancelado")
        else:
            parts.append("fuera de la red (anuncios)" if info.get("out_of_network") else "vuelta a la red")
            if "duration_s" in info:
                parts.append(_seconds(info["duration_s"]))
    for seg in info.get("segmentation", []):
        text = str(seg.get("type", ""))
        if "duration_s" in seg:
            text += " " + _seconds(seg["duration_s"])
        parts.append(text.strip())
    if "event_id" in info:
        parts.append(f"evento {info['event_id']}")
    if info.get("crc_ok") is False:
        parts.append("CRC incorrecto")
    return " · ".join(p for p in parts if p)


def decode_cue(value: str) -> dict[str, Any] | None:
    """Decode a SCTE-35 payload written as hexadecimal (``0xFC30…``) or base64, as playlists carry it."""
    text = value.strip().strip('"')
    if not text:
        return None
    try:
        if text[:2].lower() == "0x":
            data = bytes.fromhex(text[2:])
        else:
            padded = text.replace("-", "+").replace("_", "/")
            data = base64.b64decode(padded + "=" * (-len(padded) % 4))
    except (ValueError, binascii.Error):
        return None
    return decode_splice_info(data)


# ---------------------------------------------------------------- HLS playlists
ATTRIBUTE = re.compile(r'([A-Za-z0-9_-]+)=("[^"]*"|[^,]*)')


def parse_attributes(text: str) -> dict[str, str]:
    """``KEY=value,KEY2="v"`` -> ``{"KEY": "value", "KEY2": "v"}`` (keys upper-cased)."""
    return {m.group(1).upper(): m.group(2).strip().strip('"') for m in ATTRIBUTE.finditer(text)}


def _number(text: str | None) -> float | None:
    try:
        return float(text) if text not in (None, "") else None
    except ValueError:
        return None


def strip_query(url: str) -> str:
    """The URL without query or fragment: streams carry tokens there that must not be stored."""
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return url.split("?", 1)[0]
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _segment_name(line: str) -> str:
    return strip_query(line.strip()).rstrip("/").rsplit("/", 1)[-1]


def _scte_identity(scte: dict[str, Any]) -> str:
    """What identifies one message among others of the same kind: its splice or segmentation event id."""
    if "event_id" in scte:
        return f"ev{scte['event_id']}"
    for seg in scte.get("segmentation", []):
        if "event_id" in seg:
            return f"seg{seg['event_id']}"
    return ""


def _scte_duration(scte: dict[str, Any]) -> float | None:
    for source in (scte, *scte.get("segmentation", [])):
        if source.get("duration_s"):
            return float(source["duration_s"])
    return None


def _marker(
    kind: str,
    line: str,
    detail: str = "",
    ident: str = "",
    scte: dict[str, Any] | None = None,
    anchor: bool = False,
    duration: float | None = None,
) -> Marker:
    """A marker. ``anchor``: it has no identity of its own, so it takes the one of the segment that follows.

    ``duration`` is the length of the break in seconds, when the tag or the message says it.
    """
    marker: Marker = {"kind": kind, "raw": line[:MAX_RAW], "detail": detail, "ident": ident}
    if scte is not None:
        duration = duration or _scte_duration(scte)
        marker["scte"] = scte
        marker["detail"] = splice_summary(scte) + (f" · {detail}" if detail else "")
        if kind == "scte35":  # the tag does not say which: the message does
            marker["kind"] = splice_kind(scte)
        own = _scte_identity(scte)
        if own:
            marker["ident"], anchor = own, False
    if duration:
        marker["duration"] = duration
    if anchor:
        marker["anchor"] = True
    return marker


def _duration_text(duration: float | None) -> str:
    return _seconds(duration) if duration is not None else ""


def _from_tag(line: str) -> Marker | None:
    """The marker a playlist tag is, or ``None`` if the tag has nothing to do with ad breaks."""
    name, _, value = line[1:].partition(":")
    name = name.strip().upper()
    attrs = parse_attributes(value) if "=" in value else {}
    scte = decode_cue(attrs.get("SCTE35", ""))

    if name == "EXT-X-CUE-OUT-CONT":
        elapsed, duration = _number(attrs.get("ELAPSEDTIME")), _number(attrs.get("DURATION"))
        if not attrs and "/" in value:  # Adobe style: elapsed/total
            left, _, right = value.partition("/")
            elapsed, duration = _number(left), _number(right)
        detail = f"{_seconds(elapsed)} de {_seconds(duration)}" if elapsed is not None and duration else ""
        marker = _marker("cue-out-cont", line, detail, "cont", scte, duration=duration)
        if elapsed is not None:
            marker["elapsed"] = elapsed
        return marker
    if name == "EXT-X-CUE-OUT":
        duration = _number(attrs.get("DURATION")) if attrs else _number(value)
        return _marker("cue-out", line, _duration_text(duration), "out", scte, anchor=True, duration=duration)
    if name == "EXT-X-CUE-IN":
        return _marker("cue-in", line, "", "in", scte, anchor=True)
    if name == "EXT-X-CUE":
        detail = _duration_text(_number(attrs.get("DURATION")))
        return _marker("cue", line, detail, attrs.get("ID", "cue"), anchor="ID" not in attrs)
    if name == "EXT-X-SCTE35":
        cue = decode_cue(attrs.get("CUE", ""))
        flag = attrs.get("CUE-OUT", "").upper()
        kind = "cue-out" if flag == "YES" else "cue-in" if flag == "NO" else "scte35"
        return _marker(kind, line, attrs.get("TYPE", ""), attrs.get("ID", "scte35"), cue, anchor="ID" not in attrs)
    if name in ("EXT-OATCLS-SCTE35", "EXT-X-SPLICEPOINT-SCTE35"):
        return _marker("scte35", line, "", "cue", decode_cue(value), anchor=True)
    if name == "EXT-X-DATERANGE":
        return _daterange(line, attrs)
    if name == "EXT-X-ASSET":
        return _marker("asset", line, attrs.get("CAID", ""), attrs.get("CAID", "asset"))
    if "SCTE" in name or "CUE" in name:  # a variant we do not know: keep it rather than lose it
        return _marker("scte35", line, "", name, anchor=True)
    return None


def _daterange(line: str, attrs: dict[str, str]) -> Marker | None:
    ident = attrs.get("ID", "")
    duration = _number(attrs.get("DURATION")) or _number(attrs.get("PLANNED-DURATION"))
    extra = _seconds(duration) if duration else ""
    for attr, kind in (("SCTE35-OUT", "cue-out"), ("SCTE35-IN", "cue-in"), ("SCTE35-CMD", "scte35")):
        if attr in attrs:
            cue = decode_cue(attrs[attr])
            return _marker(kind, line, extra, f"{ident}/{attr[7:].lower()}", cue, duration=duration)
    klass = attrs.get("CLASS", "")
    if klass == "com.apple.hls.interstitial" or "X-ASSET-URI" in attrs or "X-ASSET-LIST" in attrs:
        return _marker("interstitial", line, extra, ident)
    if not ident and not klass:
        return None
    return _marker("daterange", line, (klass + " " + extra).strip(), ident)


def scan_playlist(text: str) -> list[Marker]:
    """Every ad-break marker in an HLS playlist, in order. Each has ``kind``, ``raw``, ``detail``, ``ident``.

    ``ident`` tells apart two markers of the same kind (it includes the segment that follows when the tag has
    no identifier of its own), so that the same break seen again in the next playlist refresh can be recognised.
    ``seg`` is that segment's name and ``lead`` how many seconds it starts before the end of the playlist: where a
    player that is watching can find the marker.
    """
    markers: list[Marker] = []
    waiting: list[Marker] = []  # markers that take their identity from the segment that follows
    ahead: list[Marker] = []  # every marker since the last segment: they all say where they are (``seg``, ``lead``)
    position = 0.0  # seconds from the start of the playlist to the segment being read
    length = 0.0  # duration announced by the last #EXTINF
    starts: dict[int, float] = {}  # id(marker) -> where its segment starts
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#EXTINF:"):
            length = _number(line[8:].split(",", 1)[0]) or 0.0
            continue
        if not line.startswith("#"):
            name = _segment_name(line)
            for marker in ahead:
                marker["seg"] = name
                starts[id(marker)] = position
            for marker in waiting:
                marker["ident"] = f"{marker['ident']}@{name}"
            ahead.clear()
            waiting.clear()
            position += length
            length = 0.0
            continue
        marker = _from_tag(line)
        if marker is None:
            continue
        if marker.pop("anchor", False):
            waiting.append(marker)
        ahead.append(marker)
        markers.append(marker)
    for marker in markers:
        if id(marker) in starts:  # how far before the end of the playlist (the live edge) its segment starts
            marker["lead"] = round(position - starts[id(marker)], 3)
    return markers


# ---------------------------------------------------------------- media segments
def _sync_offset(data: bytes) -> int | None:
    """Where the 188-byte packets of an MPEG-TS sample start (the sample may begin mid-packet)."""
    for start in range(min(TS_PACKET, len(data))):
        positions = range(start, min(len(data), start + 4 * TS_PACKET), TS_PACKET)
        if len(positions) >= 2 and all(data[p] == 0x47 for p in positions):
            return start
    return None


def _has_cuei(descriptors: bytes) -> bool:
    pos = 0
    while pos + 2 <= len(descriptors):
        tag, length = descriptors[pos], descriptors[pos + 1]
        if tag == 0x05 and descriptors[pos + 2 : pos + 6] == b"CUEI":
            return True
        pos += 2 + length
    return False


class _TsScan:
    """Follows PAT -> PMT -> SCTE-35 PIDs through the packets of a sample."""

    def __init__(self) -> None:
        self.pmt_pids: set[int] = set()
        self.scte_pids: set[int] = set()
        self.found: dict[int, str] = {}  # pid -> how it was recognised
        self.cues: list[dict[str, Any]] = []
        self.programs = 0
        self.cuei = False
        self.buffers: dict[int, bytearray] = {}

    def wants(self, pid: int) -> bool:
        return pid == 0 or pid in self.pmt_pids or pid in self.scte_pids

    def feed(self, packet: bytes) -> None:
        pid = ((packet[1] & 0x1F) << 8) | packet[2]
        if not self.wants(pid):
            return
        control = (packet[3] >> 4) & 3
        start = 4 + (1 + packet[4] if control & 2 else 0)
        if not control & 1 or start >= TS_PACKET:
            return
        payload = packet[start:]
        if packet[1] & 0x40:  # a section starts here, after the tail of the previous one
            skip = 1 + payload[0]
            if pid in self.buffers and skip > 1:
                self.buffers[pid].extend(payload[1:skip])
                self._drain(pid)
            self.buffers[pid] = bytearray(payload[skip:])
        elif pid in self.buffers:
            self.buffers[pid].extend(payload)
        else:
            return
        self._drain(pid)

    def _drain(self, pid: int) -> None:
        buffer = self.buffers[pid]
        while len(buffer) >= 3 and buffer[0] != 0xFF:
            size = 3 + (((buffer[1] & 0x0F) << 8) | buffer[2])
            if len(buffer) < size:
                return
            self._section(pid, bytes(buffer[:size]))
            del buffer[:size]
        if not buffer or buffer[0] == 0xFF:  # nothing left, or only stuffing
            self.buffers.pop(pid, None)

    def _section(self, pid: int, section: bytes) -> None:
        table = section[0]
        if pid == 0 and table == 0x00:
            for pos in range(8, len(section) - 4, 4):
                number = int.from_bytes(section[pos : pos + 2], "big")
                if number:
                    self.programs += 1
                    self.pmt_pids.add(int.from_bytes(section[pos + 2 : pos + 4], "big") & 0x1FFF)
        elif pid in self.pmt_pids and table == 0x02:
            self._pmt(section)
        elif pid in self.scte_pids and table == 0xFC:
            info = decode_splice_info(section)
            if info is not None and len(self.cues) < 20:
                self.cues.append(info)

    def _pmt(self, section: bytes) -> None:
        program_info = ((section[10] & 0x0F) << 8) | section[11]
        if _has_cuei(section[12 : 12 + program_info]):
            self.cuei = True
        pos, end = 12 + program_info, len(section) - 4
        while pos + 5 <= end:
            stream_type = section[pos]
            pid = ((section[pos + 1] & 0x1F) << 8) | section[pos + 2]
            info_length = ((section[pos + 3] & 0x0F) << 8) | section[pos + 4]
            descriptors = section[pos + 5 : pos + 5 + info_length]
            if stream_type == SCTE_STREAM_TYPE:
                self.found[pid] = "stream_type 0x86"
            elif _has_cuei(descriptors):
                self.found[pid] = "descriptor CUEI"
            if pid in self.found:
                self.scte_pids.add(pid)
            pos += 5 + info_length


def inspect_ts(data: bytes) -> dict[str, Any] | None:
    """SCTE-35 PIDs declared in the PMTs of an MPEG-TS sample, and the messages seen on them.

    ``None`` if the sample is not MPEG-TS. Otherwise ``{"programs", "pids": {pid: how}, "cues": [...], "cuei"}``.
    """
    start = _sync_offset(data)
    if start is None:
        return None
    scan = _TsScan()
    for offset in range(start, len(data) - TS_PACKET + 1, TS_PACKET):
        packet = data[offset : offset + TS_PACKET]
        if packet[0] == 0x47:
            try:
                scan.feed(packet)
            except IndexError:  # a damaged section: carry on with the next packet
                scan.buffers.clear()
    return {"programs": scan.programs, "pids": dict(scan.found), "cues": scan.cues, "cuei": scan.cuei}


def has_scte_emsg(data: bytes) -> bool:
    """True if a fragmented-MP4 sample carries SCTE-35 in ``emsg`` boxes."""
    return any(scheme in data for scheme in EMSG_SCHEMES)


def segment_markers(data: bytes) -> list[Marker]:
    """Markers found in the first bytes of a media segment (MPEG-TS or fragmented MP4)."""
    ts = inspect_ts(data)
    markers: list[Marker] = []
    if ts is not None:
        for pid, how in ts["pids"].items():
            markers.append(_marker("ts-pid", f"PID 0x{pid:04x} ({how})", f"PID {pid} ({how})", f"pid{pid}"))
        if ts["cuei"] and not ts["pids"]:
            markers.append(_marker("ts-pid", "registro CUEI en el programa", "registro CUEI en el programa", "cuei"))
        for cue in ts["cues"]:
            markers.append(_marker("scte35", "mensaje en el TS", "", "ts", cue))
    elif has_scte_emsg(data):
        markers.append(_marker("emsg", "emsg urn:scte:scte35:2013", "eventos SCTE-35 en fMP4", "emsg"))
    return markers
