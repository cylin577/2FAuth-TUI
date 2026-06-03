from __future__ import annotations

import json
from pathlib import Path

from platformdirs import user_config_dir


def app_dir() -> Path:
    return Path(user_config_dir("2FAuth-TUI", "2FAuth-TUI"))


def local_bin_dir() -> Path:
    return Path.home() / ".local" / "bin"


def launcher_file() -> Path:
    return local_bin_dir() / "2fauth"


CONFIG_FILE = app_dir() / "config.json"
PAT_FILE = app_dir() / "pat.token"
PASSWORD_FILE = app_dir() / "password.json"


def ensure_app_dir() -> None:
    app_dir().mkdir(parents=True, exist_ok=True)
    try:
        app_dir().chmod(0o700)
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


def launcher_exists() -> bool:
    return launcher_file().exists()


def install_launcher(repo_root: Path) -> Path:
    """Install a shell launcher in ~/.local/bin/2fauth."""
    local_bin_dir().mkdir(parents=True, exist_ok=True)
    script = "\n".join(
        [
            "#!/usr/bin/env sh",
            f'exec uv run --directory "{repo_root}" 2FAuth-TUI "$@"',
            "",
        ]
    )
    path = launcher_file()
    path.write_text(script, encoding="utf-8")
    try:
        path.chmod(0o755)
    except OSError:
        pass
    return path
