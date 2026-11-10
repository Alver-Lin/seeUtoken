"""Match Cursor usage records to local user questions, using conversation and time."""

from __future__ import annotations

import json
import sqlite3
from bisect import bisect_right
from contextlib import closing
from datetime import datetime
from pathlib import Path

from .auth import cursor_state_db_path

# Usage events can land a moment before the local user bubble timestamp is written.
_EVENT_TIME_SKEW_MS = 5_000


def _question_time(header: dict) -> int:
    try:
        if header.get("startedAtMs"):
            return int(header["startedAtMs"])
        value = header.get("createdAt")
        if isinstance(value, str):
            return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)
        return int(value or 0)
    except (ValueError, TypeError, OverflowError):
        return 0


def _is_user_question_text(text: str) -> bool:
    value = text.strip()
    if not value:
        return False
    # Agent transcripts inject synthetic notification bubbles; skip them as prompts.
    if value.startswith("<timestamp>") and "<system_notification" in value[:240]:
        return False
    return True


def _questions_from_headers(composer: dict) -> list[tuple[int, str]]:
    questions = [
        (at, header["bubbleId"])
        for header in composer.get("fullConversationHeadersOnly", [])
        if isinstance(header, dict) and header.get("type") == 1
        and header.get("bubbleId") and (at := _question_time(header)) > 0
    ]
    questions.sort(key=lambda item: item[0])
    return questions


def _questions_from_bubbles(conn: sqlite3.Connection, cid: str) -> list[tuple[int, str]]:
    """Newer agent chats may leave fullConversationHeadersOnly empty; read user bubbles directly."""
    prefix = f"bubbleId:{cid}:"
    rows = conn.execute(
        "SELECT key, value FROM cursorDiskKV WHERE key LIKE ?",
        (f"{prefix}%",),
    ).fetchall()
    questions: list[tuple[int, str]] = []
    for key, raw in rows:
        if not key.startswith(prefix):
            continue
        suffix = key[len(prefix):]
        # Skip tool/step derivatives like ".../s:12" or ".../t:call-...".
        if "/" in suffix:
            continue
        try:
            bubble = json.loads(raw)
        except (ValueError, TypeError):
            continue
        if not isinstance(bubble, dict) or bubble.get("type") != 1:
            continue
        text = bubble.get("text")
        if not isinstance(text, str) or not _is_user_question_text(text):
            continue
        at = _question_time(bubble)
        if at <= 0:
            continue
        questions.append((at, str(bubble.get("bubbleId") or suffix)))
    questions.sort(key=lambda item: item[0])
    return questions


def _read_bubble_text(conn: sqlite3.Connection, cid: str, bubble_id: str) -> str:
    raw = conn.execute(
        "SELECT value FROM cursorDiskKV WHERE key = ?",
        (f"bubbleId:{cid}:{bubble_id}",),
    ).fetchone()
    try:
        bubble = json.loads(raw[0]) if raw else {}
        if bubble.get("type") == 1 and isinstance(bubble.get("text"), str):
            text = bubble["text"].strip()
            return text if _is_user_question_text(text) else ""
    except (ValueError, TypeError, AttributeError):
        pass
    return ""


def add_cursor_questions(events: list[dict], db_path: Path | None = None) -> list[dict]:
    """Enrich detail rows only. Read exact user bubble keys, never authentication rows."""
    rows = [{**event, "prompt": event.get("prompt") or ""} for event in events]
    conversations = {}
    for row in rows:
        cid = row.get("conversationId")
        if cid and not row["prompt"]:
            conversations.setdefault(str(cid), []).append(row)
    if not conversations:
        return rows
    path = db_path if db_path is not None else cursor_state_db_path()
    if not path.is_file():
        return rows
    try:
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=1)) as conn:
            for cid, selected in conversations.items():
                raw = conn.execute("SELECT value FROM cursorDiskKV WHERE key = ?", (f"composerData:{cid}",)).fetchone()
                questions: list[tuple[int, str]] = []
                if raw:
                    try:
                        composer = json.loads(raw[0])
                        if isinstance(composer, dict):
                            questions = _questions_from_headers(composer)
                    except (ValueError, TypeError, AttributeError):
                        questions = []
                if not questions:
                    try:
                        questions = _questions_from_bubbles(conn, cid)
                    except (ValueError, TypeError, AttributeError, sqlite3.Error):
                        continue
                if not questions:
                    continue
                times = [at for at, _ in questions]
                texts = {}
                for row in selected:
                    try:
                        event_time = int(row.get("time") or 0)
                        index = bisect_right(times, event_time) - 1
                        # Usage can stamp a few ms before the local bubble timestamp.
                        nxt = index + 1
                        if nxt < len(times):
                            delta_next = times[nxt] - event_time
                            if 0 < delta_next <= _EVENT_TIME_SKEW_MS:
                                delta_prev = event_time - times[index] if index >= 0 else None
                                if delta_prev is None or delta_next < delta_prev:
                                    index = nxt
                    except (ValueError, TypeError, OverflowError):
                        continue
                    if index < 0:
                        continue
                    bubble_id = questions[index][1]
                    if bubble_id not in texts:
                        texts[bubble_id] = _read_bubble_text(conn, cid, bubble_id)
                    row["prompt"] = texts[bubble_id]
    except (OSError, sqlite3.Error):
        pass  # Missing/locked local history must not interrupt usage reporting.
    return rows
