"""Match Cursor usage records to local user questions, using conversation and time."""

from __future__ import annotations

import json
import sqlite3
from bisect import bisect_right
from contextlib import closing
from datetime import datetime
from pathlib import Path

from .auth import cursor_state_db_path


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
                if not raw:
                    continue
                try:
                    composer = json.loads(raw[0])
                    questions = [
                        (at, header["bubbleId"])
                        for header in composer.get("fullConversationHeadersOnly", [])
                        if isinstance(header, dict) and header.get("type") == 1
                        and header.get("bubbleId") and (at := _question_time(header)) > 0
                    ]
                    questions.sort(key=lambda item: item[0])
                except (ValueError, TypeError, AttributeError):
                    continue
                times = [at for at, _ in questions]
                texts = {}
                for row in selected:
                    try:
                        index = bisect_right(times, int(row.get("time") or 0)) - 1
                    except (ValueError, TypeError, OverflowError):
                        continue
                    if index < 0:
                        continue
                    bubble_id = questions[index][1]
                    if bubble_id not in texts:
                        raw = conn.execute("SELECT value FROM cursorDiskKV WHERE key = ?",
                                           (f"bubbleId:{cid}:{bubble_id}",)).fetchone()
                        text = ""
                        try:
                            bubble = json.loads(raw[0]) if raw else {}
                            if bubble.get("type") == 1 and isinstance(bubble.get("text"), str):
                                text = bubble["text"].strip()
                        except (ValueError, TypeError, AttributeError):
                            pass
                        texts[bubble_id] = text
                    row["prompt"] = texts[bubble_id]
    except (OSError, sqlite3.Error):
        pass  # Missing/locked local history must not interrupt usage reporting.
    return rows
