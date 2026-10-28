"""从本机 Cursor 项目目录解析 conversationId → 项目名。"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

_cache: dict[str, Any] = {"ts": 0.0, "map": {}}
_CACHE_TTL_SEC = 60.0


def cursor_projects_root() -> Path:
    return Path.home() / ".cursor" / "projects"


def project_display_name(slug: str) -> str:
    """Users-xxx-Desktop-seeUtoken → seeUtoken。"""
    text = str(slug or "").strip()
    if not text:
        return ""
    for marker in (
        "Desktop-",
        "Documents-",
        "Downloads-",
        "Projects-",
        "repos-",
        "code-",
        "dev-",
        "work-",
    ):
        if marker in text:
            name = text.split(marker, 1)[1].strip("-")
            return name or text
    return text


def _scan_conversation_projects() -> dict[str, str]:
    """conversationId → 展示用项目名。"""
    root = cursor_projects_root()
    out: dict[str, str] = {}
    if not root.is_dir():
        return out
    try:
        for proj in root.iterdir():
            if not proj.is_dir():
                continue
            name = project_display_name(proj.name)
            transcripts = proj / "agent-transcripts"
            if not transcripts.is_dir():
                continue
            try:
                for d in transcripts.iterdir():
                    if d.is_dir() and len(d.name) >= 8:
                        out[d.name] = name
            except OSError:
                continue
    except OSError:
        return out
    return out


def conversation_project_map(*, force: bool = False) -> dict[str, str]:
    now = time.time()
    if (
        not force
        and _cache["map"]
        and now - float(_cache["ts"] or 0) < _CACHE_TTL_SEC
    ):
        return _cache["map"]
    mapping = _scan_conversation_projects()
    _cache["map"] = mapping
    _cache["ts"] = now
    return mapping


def resolve_project_name(conversation_id: str | None, mapping: dict[str, str] | None = None) -> str:
    cid = str(conversation_id or "").strip()
    if not cid:
        return ""
    m = mapping if mapping is not None else conversation_project_map()
    return m.get(cid) or ""
