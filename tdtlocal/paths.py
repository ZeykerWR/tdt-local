"""Where the program keeps its files.

Run from a source checkout it keeps ``data/`` and ``models/`` next to the code. Installed (wheel, installer,
frozen app) it uses the per-user location each operating system expects, because the install folder is
usually read-only.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "TDT local"


def is_source_checkout(project_dir: Path) -> bool:
    """True when ``project_dir`` is the repository root (it has ``pyproject.toml``) and we are not frozen."""
    return not getattr(sys, "frozen", False) and (project_dir / "pyproject.toml").is_file()


def user_data_dir(platform: str | None = None, env: dict[str, str] | None = None, home: Path | None = None) -> Path:
    """Per-user data directory: ``%LOCALAPPDATA%\\TDT local``, ``~/Library/Application Support/TDT local`` or
    ``$XDG_DATA_HOME/tdt-local``. Arguments exist so every platform can be tested from any platform."""
    platform = platform or sys.platform
    env = os.environ if env is None else env
    home = home or Path.home()
    if platform.startswith("win"):
        return Path(env.get("LOCALAPPDATA") or home / "AppData" / "Local") / APP_NAME
    if platform == "darwin":
        return home / "Library" / "Application Support" / APP_NAME
    return Path(env.get("XDG_DATA_HOME") or home / ".local" / "share") / "tdt-local"


def default_data_dir(project_dir: Path) -> Path:
    return project_dir / "data" if is_source_checkout(project_dir) else user_data_dir()


def default_models_dir(project_dir: Path) -> Path:
    return project_dir / "models" if is_source_checkout(project_dir) else user_data_dir() / "models"
