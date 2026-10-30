"""Read Codex task lifecycle markers without using CPU as a busy signal."""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path


class CodexActivity:
    # Ignore orphaned logs after a crash. Normal completion/abort stops at once.
    STALE_SECONDS = 20 * 60

    def __init__(self, home: Path | None = None):
        self.home = home or Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
        self._files: dict = {}
        self._lock = threading.Lock()
        self._live_files: set[Path] = set()
        self._live_checked = 0.0
        self._live_running = False

    def _refresh_live_files(self):
        """Windows rollouts may stay buffered during a long-running turn."""
        live = set()
        try:
            import psutil

            for process in psutil.process_iter(['name']):
                if (process.info.get('name') or '').lower() != 'codex.exe':
                    continue
                try:
                    for opened in process.open_files():
                        path = Path(opened.path)
                        if path.suffix == '.jsonl' and path.is_relative_to(self.home):
                            live.add(path)
                except (psutil.Error, OSError):
                    continue
        except (ImportError, OSError):
            pass
        finally:
            with self._lock:
                self._live_files = live
                self._live_checked = time.monotonic()
                self._live_running = False

    def probe(self, now: float | None = None) -> dict:
        current = time.time() if now is None else now
        with self._lock:
            if sys.platform == 'win32' and not self._live_running and time.monotonic() - self._live_checked >= 5:
                self._live_running = True
                # Process handle enumeration must never block the activity API.
                threading.Thread(target=self._refresh_live_files, daemon=True).start()
            found = set()
            active = 0
            for path in (self.home / "sessions").rglob("*.jsonl"):
                try:
                    stat = path.stat()
                    live_writer = sys.platform == 'win32' and path in self._live_files
                    if current - stat.st_mtime > self.STALE_SECONDS and not live_writer:
                        continue
                    found.add(path)
                    cached = self._files.get(path)
                    # A replaced/truncated rollout must not inherit a busy state.
                    if not cached or cached["inode"] != stat.st_ino or stat.st_size < cached["offset"]:
                        cached = {"inode": stat.st_ino, "offset": 0, "signature": None,
                                  "turn": None, "model": ""}
                    signature = (stat.st_size, stat.st_mtime_ns)
                    if cached["signature"] != signature:
                        with path.open("rb") as stream:
                            stream.seek(cached["offset"])
                            while True:
                                line = stream.readline()
                                if not line or not line.endswith(b"\n"):
                                    break  # retry an incomplete last line next poll
                                cached["offset"] = stream.tell()
                                if not any(marker in line for marker in (
                                    b'"task_started"', b'"task_complete"',
                                    b'"turn_aborted"', b'"turn_context"',
                                )):
                                    continue
                                try:
                                    record = json.loads(line)
                                    payload = record.get("payload") or {}
                                    if record.get("type") == "turn_context":
                                        cached["model"] = payload.get("model") or cached["model"]
                                    elif record.get("type") == "event_msg":
                                        kind = payload.get("type")
                                        turn = payload.get("turn_id")
                                        if kind == "task_started":
                                            cached["turn"] = turn or "current"
                                        elif kind in ("task_complete", "turn_aborted"):
                                            if not turn or cached["turn"] in (turn, "current"):
                                                cached["turn"] = None
                                except (ValueError, TypeError, AttributeError):
                                    continue
                        cached["signature"] = signature
                    self._files[path] = cached
                    if cached["turn"] and cached["model"] != "codex-auto-review":
                        active += 1
                except OSError:
                    continue
            self._files = {path: state for path, state in self._files.items() if path in found}
            return {"ok": True, "busy": active > 0, "activeTasks": active}
