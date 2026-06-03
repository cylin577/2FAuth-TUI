from __future__ import annotations

import json
import os
from pathlib import Path

from platformdirs import user_config_dir

APP_DIR = Path(user_config_dir("2FAuth-TUI", "2FAuth-TUI"))
CONFIG_FILE = APP_DIR / "config.json"
PAT_FILE = APP_DIR / "pat.token"
PASSWORD_FILE = APP_DIR / "password.json"


def ensure_app_dir() -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    try:
        APP_DIR.chmod(0o700)
    except OSError:
        pass


def save_text(path: Path, text: str) -> None:
    ensure_app_dir()
    path.write_text(text, encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def save_json(path: Path, data: dict[str, object]) -> None:
    ensure_app_dir()
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def load_json(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def load_text(path: Path) -> str | None:
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8").strip()


def has_setup() -> bool:
    return CONFIG_FILE.exists() and PAT_FILE.exists() and PASSWORD_FILE.exists()
