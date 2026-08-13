"""Persisting a logged-in session between runs.

TGTG's login needs a PIN typed from an email, which is fine once but tedious
every run. The refresh token outlives the access token by a long way, so the
tokens are kept on disk and refreshed on startup instead.

The file lives outside the repository, under XDG_CONFIG_HOME (or ~/.config), so
it cannot be committed by accident, and is written 0600 because a refresh token
is as good as a password.
"""

import json
import os
import time
from pathlib import Path

APP_DIR = "tgtg_auto"
FILE_NAME = "session.json"

FIELDS = ("email", "access_token", "refresh_token", "cookie", "user_agent")


def session_path() -> Path:
    root = os.environ.get("XDG_CONFIG_HOME")
    base = Path(root).expanduser() if root else Path.home() / ".config"
    return base / APP_DIR / FILE_NAME


def load() -> dict | None:
    path = session_path()
    try:
        with path.open() as handle:
            stored = json.load(handle)
    except (OSError, ValueError):
        return None

    # a session missing its tokens is worse than no session at all
    if not stored.get("access_token") or not stored.get("refresh_token"):
        return None
    return stored


def save(client, email: str | None = None) -> Path:
    path = session_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "email": email or getattr(client, "email", None),
        "access_token": client.access_token,
        "refresh_token": client.refresh_token,
        "cookie": client.cookie,
        "user_agent": client.user_agent,
        "saved_at": time.time(),
    }

    # opened 0600 up front rather than chmod'ed afterwards, so the tokens are
    # never briefly readable by anyone else
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as handle:
        json.dump(payload, handle)
    return path


def clear() -> bool:
    try:
        session_path().unlink()
        return True
    except OSError:
        return False


def age_days(stored: dict) -> float | None:
    saved_at = stored.get("saved_at")
    return (time.time() - saved_at) / 86400 if saved_at else None
