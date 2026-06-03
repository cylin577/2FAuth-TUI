from __future__ import annotations

import base64
import hashlib
import json
import secrets
from pathlib import Path

PASSWORD_ALGO = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 310_000


def make_password_record(password: str) -> dict[str, str | int]:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_ITERATIONS,
        dklen=32,
    )
    return {
        "algorithm": PASSWORD_ALGO,
        "iterations": PASSWORD_ITERATIONS,
        "salt_b64": base64.b64encode(salt).decode("ascii"),
        "hash_b64": base64.b64encode(digest).decode("ascii"),
    }


def verify_password(password: str, record: dict[str, object]) -> bool:
    if record.get("algorithm") != PASSWORD_ALGO:
        return False
    try:
        salt = base64.b64decode(str(record["salt_b64"]))
        expected = base64.b64decode(str(record["hash_b64"]))
        iterations = int(record["iterations"])
    except Exception:
        return False

    actual = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
        dklen=len(expected),
    )
    return secrets.compare_digest(actual, expected)


def read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, object]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
