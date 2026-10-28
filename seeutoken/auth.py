"""从本机 Cursor 登录态或手动 Token 解析会话 Cookie。"""

from __future__ import annotations

import base64
import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any
from urllib.parse import unquote

# 避免反复读大体积 state.vscdb
_token_cache: dict[str, Any] = {"token": None, "mtime": None, "ts": 0.0}
_TOKEN_TTL_SEC = 90.0


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


def _query_access_token(conn: sqlite3.Connection) -> str | None:
    cur = conn.execute(
        "SELECT value FROM ItemTable WHERE key = ? LIMIT 1",
        ("cursorAuth/accessToken",),
    )
    row = cur.fetchone()
    if not row:
        return None
    token = row[0]
    return token if isinstance(token, str) and len(token) > 20 else None


def read_access_token_from_db() -> str | None:
    """只读打开 Cursor 登录库；带 mtime 缓存，绝不全量复制数 GB 的 db。"""
    db_path = cursor_state_db_path()
    if not db_path.exists():
        return None

    try:
        mtime = db_path.stat().st_mtime
    except OSError:
        mtime = None

    now = time.time()
    if (
        _token_cache["token"]
        and _token_cache["mtime"] == mtime
        and now - float(_token_cache["ts"] or 0) < _TOKEN_TTL_SEC
    ):
        return _token_cache["token"]

    token: str | None = None
    uri = db_path.resolve().as_uri() + "?mode=ro"

    # 1) 只读 URI（不复制文件）
    try:
        conn = sqlite3.connect(uri, uri=True, timeout=3)
        try:
            token = _query_access_token(conn)
        finally:
            conn.close()
    except Exception:
        token = None

    # 2) 直接打开（部分平台 URI 失败时）
    if not token:
        try:
            conn = sqlite3.connect(f"file:{db_path.resolve().as_posix()}?mode=ro", uri=True, timeout=3)
            try:
                token = _query_access_token(conn)
            finally:
                conn.close()
        except Exception:
            token = None

    if token:
        _token_cache["token"] = token
        _token_cache["mtime"] = mtime
        _token_cache["ts"] = now
    return token


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


def extract_jwt(cookie_or_token: str | None) -> str | None:
    """从 WorkosCursorSessionToken（userId::jwt）或纯 JWT 取出 Bearer token。"""
    if not cookie_or_token:
        return None
    raw = str(cookie_or_token).strip()
    try:
        raw = unquote(raw)
    except Exception:
        pass
    if "::" in raw:
        jwt = raw.split("::", 1)[1].strip()
        return jwt or None
    if raw.count(".") >= 2 and decode_jwt_payload(raw):
        return raw
    return None


def resolve_session_token(manual_token: str | None = None) -> dict[str, Any]:
    if manual_token:
        cookie = to_session_cookie_value(manual_token)
        if cookie:
            return {"cookie": cookie, "jwt": extract_jwt(cookie), "source": "manual"}

    try:
        jwt = read_access_token_from_db()
        if jwt:
            cookie = to_session_cookie_value(jwt)
            if cookie:
                return {
                    "cookie": cookie,
                    "jwt": jwt,
                    "source": "cursor-db",
                    "dbPath": str(cursor_state_db_path()),
                }
    except Exception as exc:
        return {"cookie": None, "jwt": None, "source": "error", "error": str(exc)}

    return {"cookie": None, "jwt": None, "source": "none"}
