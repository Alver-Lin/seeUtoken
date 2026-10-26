"""从本机 Cursor 登录态或手动 Token 解析会话 Cookie。"""

from __future__ import annotations

import base64
import json
import os
import shutil
import sqlite3
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import unquote


def cursor_state_db_path() -> Path:
    if os.name == "nt":
        appdata = os.environ.get("APPDATA", "")
        return Path(appdata) / "Cursor" / "User" / "globalStorage" / "state.vscdb"
    home = Path.home()
    if Path("/Applications").exists() and (home / "Library").exists():
        return (
            home
            / "Library"
            / "Application Support"
            / "Cursor"
            / "User"
            / "globalStorage"
            / "state.vscdb"
        )
    return home / ".config" / "Cursor" / "User" / "globalStorage" / "state.vscdb"


def decode_jwt_payload(jwt: str) -> dict[str, Any] | None:
    try:
        part = jwt.split(".")[1]
        pad = "=" * (-len(part) % 4)
        raw = base64.urlsafe_b64decode(part + pad)
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return None


def read_access_token_from_db() -> str | None:
    db_path = cursor_state_db_path()
    if not db_path.exists():
        return None

    tmp = Path(tempfile.gettempdir()) / f"seeutoken-state-{os.getpid()}.vscdb"
    try:
        shutil.copy2(db_path, tmp)
        conn = sqlite3.connect(str(tmp))
        try:
            cur = conn.execute(
                "SELECT value FROM ItemTable WHERE key = ? LIMIT 1",
                ("cursorAuth/accessToken",),
            )
            row = cur.fetchone()
            if not row:
                return None
            token = row[0]
            return token if isinstance(token, str) and len(token) > 20 else None
        finally:
            conn.close()
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def to_session_cookie_value(token_or_cookie: str | None) -> str | None:
    if not token_or_cookie:
        return None
    raw = str(token_or_cookie).strip()
    try:
        raw = unquote(raw)
    except Exception:
        pass

    if "::" in raw:
        return raw
    if "%3A%3A" in raw.upper():
        return unquote(raw)

    payload = decode_jwt_payload(raw)
    sub = (payload or {}).get("sub")
    if not sub:
        return None
    return f"{sub}::{raw}"


def resolve_session_token(manual_token: str | None = None) -> dict[str, Any]:
    if manual_token:
        cookie = to_session_cookie_value(manual_token)
        if cookie:
            return {"cookie": cookie, "source": "manual"}

    try:
        jwt = read_access_token_from_db()
        if jwt:
            cookie = to_session_cookie_value(jwt)
            if cookie:
                return {
                    "cookie": cookie,
                    "source": "cursor-db",
                    "dbPath": str(cursor_state_db_path()),
                }
    except Exception as exc:
        return {"cookie": None, "source": "error", "error": str(exc)}

    return {"cookie": None, "source": "none"}
