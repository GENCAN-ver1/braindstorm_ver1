"""Atomic, allowlisted persistence for web-host session metadata."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping


class SessionStoreError(RuntimeError):
    pass


class SessionStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def session_dir(self, session_id: str) -> Path:
        if not _valid_session_id(session_id):
            raise SessionStoreError("invalid session id")
        target = (self.root / session_id).resolve()
        if target.parent != self.root:
            raise SessionStoreError("invalid session path")
        return target

    def load(self, session_id: str) -> dict[str, Any]:
        target = self.session_dir(session_id) / "session.json"
        try:
            value = json.loads(target.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise SessionStoreError("session not found") from None
        except (OSError, UnicodeError, json.JSONDecodeError):
            raise SessionStoreError("session data is unavailable") from None
        if not isinstance(value, dict) or value.get("id") != session_id:
            raise SessionStoreError("session data is invalid")
        return value

    def save(self, session: Mapping[str, Any]) -> None:
        session_id = session.get("id")
        if not isinstance(session_id, str):
            raise SessionStoreError("session id is missing")
        directory = self.session_dir(session_id)
        directory.mkdir(parents=True, exist_ok=True)
        try:
            payload = (
                json.dumps(
                    session,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                    allow_nan=False,
                )
                + "\n"
            )
        except (TypeError, ValueError):
            raise SessionStoreError("session data is invalid") from None
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".session.", suffix=".tmp", dir=directory
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, directory / "session.json")
        except Exception:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
            raise


def _valid_session_id(value: str) -> bool:
    if not isinstance(value, str) or not value.startswith("session-"):
        return False
    suffix = value.removeprefix("session-")
    return len(suffix) == 32 and all(character in "0123456789abcdef" for character in suffix)
