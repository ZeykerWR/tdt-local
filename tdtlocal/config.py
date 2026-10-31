"""Runtime configuration: defaults, paths and the :class:`Config` container."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .paths import default_data_dir, default_models_dir

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PACKAGE_DIR.parent

TV_SOURCE = "https://raw.githubusercontent.com/LaQuay/TDTChannels/master/TELEVISION.md"
RADIO_SOURCE = "https://raw.githubusercontent.com/LaQuay/TDTChannels/master/RADIO.md"
# XMLTV guides published by TDTChannels; the "EPG ID" column of the lists matches their channel ids.
EPG_SOURCES = {
    "tv": "https://www.tdtchannels.com/epg/TV.xml.gz",
    "radio": "https://www.ondachannels.com/epg/RADIO.xml.gz",
}

DEFAULT_PORT = 8788
DEFAULT_LLM_URL = "http://127.0.0.1:8080/v1"
DEFAULT_WHISPER_URL = "http://127.0.0.1:8178"

LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")


@dataclass
class Config:
    """Everything the server needs to know before it starts. Plain data, no globals."""

    host: str = "127.0.0.1"
    port: int = DEFAULT_PORT
    update_hours: float = 6.0
    auto_check: bool = False
    verbose: bool = False
    allow_quit: bool = False  # expose POST /api/quit and the "Salir" button (desktop app without a console)

    tv_source: str = TV_SOURCE
    radio_source: str = RADIO_SOURCE
    epg_enabled: bool = True
    epg_sources: dict[str, str] = field(default_factory=lambda: dict(EPG_SOURCES))

    data_dir: Path = field(default_factory=lambda: default_data_dir(PROJECT_DIR))
    models_dir: Path = field(default_factory=lambda: default_models_dir(PROJECT_DIR))
    static_dir: Path = PACKAGE_DIR / "static"

    ai_enabled: bool = True
    llm_url: str = DEFAULT_LLM_URL
    llm_model: str = ""
    llm_api_key: str = ""  # sent as a Bearer token; only needed for hosted endpoints
    llm_temperature: float = 0.2
    llm_max_tokens: int = 700
    llm_timeout: float = 120.0
    llm_disable_thinking: bool = True  # ask reasoning models not to "think": latency matters more here
    llm_extra_params: str = ""  # JSON object merged into every chat request (top_p, top_k...)

    stt_enabled: bool = True
    whisper_url: str = DEFAULT_WHISPER_URL
    whisper_bin: str = ""
    whisper_model: str = ""
    whisper_lang: str = "es"
    whisper_threads: int = 8
    whisper_idle_minutes: int = 10  # a whisper-server we launched stops after this long without work
    whisper_autostart: bool = True  # launch our own whisper-server when none answers

    allow_private: bool = False  # tests only: lets the proxy reach loopback/private addresses
    # settings fixed by a command-line flag or environment variable: the saved value is ignored
    # and the interface shows them read-only
    locked: frozenset[str] = frozenset()

    @property
    def loopback_only(self) -> bool:
        """True when the server only listens on this machine (enables the Host header check)."""
        return self.host in LOOPBACK_HOSTS

    @property
    def update_seconds(self) -> float:
        return self.update_hours * 3600
