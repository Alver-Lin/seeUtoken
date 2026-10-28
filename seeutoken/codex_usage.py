"""Codex account limits via app-server; local model/project usage via rollouts.

Only user questions appear in detail records; never expose credentials or
system/assistant messages. Normalize Codex input to exclude cache reads/writes,
matching the Cursor dashboard fields.
Keep processedTokens (including cache) separately; reasoning is part of output.
"""
from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .heatmap import aggregate_days_from_events, build_year_grid

TOKEN_FIELDS = ("input", "output", "cache", "cacheRead", "cacheWrite", "tokens", "processedTokens")


def question_text(payload: dict) -> str:
    """Extract the visible user question, excluding injected attachment/context metadata."""
    if payload.get("type") == "user_message":
        parts = [payload.get("message")]
    else:
        content = payload.get("content") or []
        parts = [content] if isinstance(content, str) else [
            item.get("text") for item in content
            if isinstance(item, dict) and item.get("type") in ("input_text", "text")
        ]
    texts = []
    for part in parts:
        if not isinstance(part, str):
            continue
        text = part.strip()
        if text.startswith("# Files mentioned by the user:"):
            _, marker, text = text.partition("## My request:")
            if not marker:
                continue
            text = text.strip()
        if not text or text.startswith((
            "<environment_context>", "<external_codex_apps_open_page>",
            "<send_user_message_question_reply>", "<subagent_notification>",
            "# AGENTS.md instructions for ", "<image ", "</image>",
        )):
            continue
        texts.append(text)
    return "\n".join(texts)


def timestamp(value: Any) -> int:
    try:
        if isinstance(value, str):
            return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)
        return int(value or 0)
    except (ValueError, TypeError, OverflowError):
        return 0


def read_account() -> dict:
    """Bounded, read-only JSON-RPC connection. Does not create threads or turns."""
    executable = shutil.which("codex")
    if not executable:
        candidates = Path("/Applications").glob("*.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex")
        executable = next((str(p) for p in candidates if p.is_file()), None)
    if not executable:
        raise RuntimeError("未找到 Codex，请先安装并登录 Codex")
    process = subprocess.Popen(
        [executable, "app-server", "--stdio"], stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
    )
    messages: queue.Queue = queue.Queue()

    def receive():
        for line in process.stdout:
            try:
                messages.put(json.loads(line))
            except ValueError:
                pass
        messages.put(None)

    threading.Thread(target=receive, daemon=True).start()
    deadline = time.monotonic() + 20

    def send(message):
        process.stdin.write(json.dumps(message) + "\n")
        process.stdin.flush()

    def rpc(identifier, method, params=None):
        send({"id": identifier, "method": method, "params": params or {}})
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError("Codex 账户同步超时")
            try:
                response = messages.get(timeout=remaining)
            except queue.Empty:
                raise RuntimeError("Codex 账户同步超时") from None
            if response is None:
                raise RuntimeError("Codex 账户服务已退出")
            if response.get("id") == identifier:
                if response.get("error"):
                    raise RuntimeError("Codex 暂未返回账户用量，请检查 Codex 登录状态")
                return response.get("result") or {}
            if "id" in response and "method" in response:
                send({"id": response["id"], "error": {"code": -32601, "message": "Unsupported request"}})

    try:
        rpc(0, "initialize", {"clientInfo": {"name": "seeutoken", "title": "seeUtoken", "version": "1.0.0"}})
        send({"method": "initialized", "params": {}})
        account = rpc(1, "account/read", {"refreshToken": False}).get("account")
        limits = rpc(2, "account/rateLimits/read")
        return {"account": account, "limits": limits, "updatedAt": int(time.time() * 1000)}
    finally:
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)
        process.stdin.close()
        process.stdout.close()


def parse_rollout(path: Path) -> dict:
    events, snapshots = [], []
    previous = None
    model, project, session = "未知模型", "—", path.stem
    turn_id = None
    turn_sequence = 0
    questions = []
    with path.open(encoding="utf-8", errors="replace") as stream:
        for line in stream:
            # Only decode user messages and usage/lifecycle metadata.
            if not any(marker in line for marker in (
                '"session_meta"', '"turn_context"', '"task_started"', '"token_count"',
                '"user_message"', '"role":"user"', '"role": "user"',
            )):
                continue
            try:
                record = json.loads(line)
                payload = record.get("payload") or {}
                kind = record.get("type")
                if not isinstance(payload, dict):
                    continue
                if kind == "session_meta":
                    session = payload.get("id") or payload.get("session_id") or session
                    project = Path(payload.get("cwd") or "").name or "—"
                elif kind == "turn_context":
                    model = payload.get("model") or model
                    project = Path(payload.get("cwd") or "").name or project
                    if payload.get("turn_id") and payload["turn_id"] != turn_id:
                        questions = []
                    turn_id = payload.get("turn_id") or turn_id
                elif kind == "event_msg" and payload.get("type") == "task_started":
                    turn_sequence += 1
                    # Older task markers may omit the ID. Each start is still a
                    # reliable boundary; never infer turns from minute buckets.
                    turn_id = payload.get("turn_id") or f"start-{record.get('timestamp')}:{turn_sequence}"
                    questions = []
                elif (kind == "response_item" and payload.get("role") == "user") or (
                    kind == "event_msg" and payload.get("type") == "user_message"
                ):
                    question = question_text(payload)
                    if question:
                        if not turn_id:
                            questions = [question]
                        elif question not in questions:
                            questions.append(question)
                elif kind == "event_msg" and payload.get("type") == "token_count":
                    ts = timestamp(record.get("timestamp"))
                    limits = payload.get("rate_limits")
                    if isinstance(limits, dict) and model != "codex-auto-review":
                        snapshots.append((ts, limits))
                    info = payload.get("info") or {}
                    total = info.get("total_token_usage")
                    last = info.get("last_token_usage")
                    if not isinstance(total, dict) or not isinstance(last, dict):
                        continue
                    keys = ("input_tokens", "cached_input_tokens", "cache_write_input_tokens", "output_tokens")
                    current = {key: max(0, int(total.get(key) or 0)) for key in keys}
                    if previous == current:
                        continue  # repeated quota snapshots are not extra calls
                    delta = {key: current[key] - previous[key] for key in keys} if previous else dict(last)
                    if any(delta.get(key, 0) < 0 for key in keys):
                        delta = dict(last)  # counter reset / context compaction
                    previous = current
                    if model == "codex-auto-review" or ts <= 0:
                        continue
                    inp = max(0, int(delta.get("input_tokens") or 0))
                    out = max(0, int(delta.get("output_tokens") or 0))
                    cache_read = min(inp, max(0, int(delta.get("cached_input_tokens") or 0)))
                    cache_write = min(inp - cache_read, max(0, int(delta.get("cache_write_input_tokens") or 0)))
                    cache = cache_read + cache_write
                    if inp + out == 0:
                        continue
                    events.append({"id": f"{session}:{ts}:{current['input_tokens']}:{current['output_tokens']}",
                                   "time": ts, "model": model, "project": project,
                                   "sessionId": session, "turnId": turn_id,
                                   "prompt": "\n".join(questions),
                                   "input": inp - cache, "output": out, "cache": cache,
                                   "cacheRead": cache_read, "cacheWrite": cache_write,
                                   "tokens": inp - cache + out, "processedTokens": inp + out})
            except (ValueError, TypeError, AttributeError):
                continue  # may be reading the last line while Codex is writing it
    return {"events": events, "snapshots": snapshots}


def summarize_turns(events: list[dict]) -> list[dict]:
    """One display row per question; keep raw calls for model/day statistics."""
    grouped = {}
    for event in events:
        turn_id = event.get("turnId")
        # Without lifecycle metadata, retaining separate legacy records is safer
        # than merging unrelated questions from the same session.
        identifier = f"{event['sessionId']}:turn:{turn_id}" if turn_id else event["id"]
        if identifier not in grouped:
            grouped[identifier] = {
                "id": identifier, "time": event["time"], "models": [], "projects": [],
                "prompt": "",
                **dict.fromkeys(TOKEN_FIELDS, 0),
            }
        row = grouped[identifier]
        if event.get("prompt") and (not row["prompt"] or event["time"] >= row["time"]):
            row["prompt"] = event["prompt"]
        row["time"] = max(row["time"], event["time"])
        for field in TOKEN_FIELDS:
            row[field] += event[field]
        for field in ("model", "project"):
            values = row[f"{field}s"]
            if event[field] not in values:
                values.append(event[field])
    rows = []
    for row in grouped.values():
        row["model"] = " / ".join(row.pop("models"))
        row["project"] = " / ".join(row.pop("projects"))
        rows.append(row)
    return sorted(rows, key=lambda row: row["time"], reverse=True)


def window_data(raw: Any, identifier: str, observed: int, now: int) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    used = raw.get("usedPercent", raw.get("used_percent"))
    minutes = raw.get("windowDurationMins", raw.get("window_minutes"))
    reset = raw.get("resetsAt", raw.get("resets_at"))
    try:
        used = min(100, max(0, float(used))) if used is not None else None
    except (TypeError, ValueError):
        used = None
    reset = int(reset) * 1000 if reset else None
    stale = bool(reset and reset <= now)
    label = f"{minutes // 1440} 天额度" if minutes and minutes % 1440 == 0 else (
        f"{minutes // 60} 小时额度" if minutes and minutes % 60 == 0 else f"{minutes} 分钟额度" if minutes else "额度窗口")
    return {"id": identifier, "label": label, "usedPercent": used,
            "remainingPercent": None if used is None or stale else 100 - used,
            "windowMinutes": minutes, "resetsAt": reset, "observedAt": observed, "stale": stale}


class CodexUsage:
    def __init__(self, home: Path | None = None):
        self.home = home or Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
        self._files: dict = {}
        self._lock = threading.Lock()
        self._remote: dict = {}
        self._remote_running = False
        self._remote_attempt: float | None = None
        self._error = None

    def _refresh_account(self):
        try:
            result = read_account()
            with self._lock:
                self._remote, self._error = result, None
        except Exception as exc:
            with self._lock:
                self._error = str(exc) if isinstance(exc, RuntimeError) else "账户暂时无法同步，显示最近额度快照"
        finally:
            with self._lock:
                self._remote_running = False

    def get(self, summary=False, year=None, refresh=False, remote=True, auto_refresh_minutes=1) -> dict:
        try:
            minutes = int(auto_refresh_minutes)
        except (TypeError, ValueError):
            minutes = 1
        if minutes not in (0, 1, 5, 15, 30):
            minutes = 1
        with self._lock:
            now_tick = time.monotonic()
            due = self._remote_attempt is None or (minutes > 0 and now_tick - self._remote_attempt >= minutes * 60)
            if remote and not self._remote_running and (refresh or due):
                self._remote_running = True
                self._remote_attempt = now_tick
                threading.Thread(target=self._refresh_account, daemon=True).start()
            found = set()
            for folder in ("sessions", "archived_sessions"):
                for path in (self.home / folder).rglob("*.jsonl"):
                    found.add(path)
                    try:
                        stat = path.stat()
                        signature = (stat.st_mtime_ns, stat.st_size)
                        if path not in self._files or self._files[path][0] != signature:
                            self._files[path] = (signature, parse_rollout(path))
                    except OSError:
                        continue
            self._files = {p: value for p, value in self._files.items() if p in found}
            # A session may have a copied rollout in archived_sessions.
            dedup = {e["id"]: e for _, parsed in self._files.values() for e in parsed["events"]}
            events = sorted(dedup.values(), key=lambda e: e["time"], reverse=True)
            snapshots = [s for _, parsed in self._files.values() for s in parsed["snapshots"] if s[1].get("limit_id") in (None, "codex")]
            observed, limits = max(snapshots, key=lambda s: s[0], default=(0, {}))
            account = self._remote.get("account") or {}
            remote_at = self._remote.get("updatedAt", 0)
            if remote_at >= observed and self._remote.get("limits"):
                result = self._remote["limits"]
                limits = result.get("rateLimitsByLimitId", {}).get("codex") or result.get("rateLimits") or {}
                observed = remote_at
            now = datetime.now().astimezone()
            now_ms = int(now.timestamp() * 1000)
            starts = {"today": now.replace(hour=0, minute=0, second=0, microsecond=0),
                      "week": (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0),
                      "month": now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)}
            periods, models = {}, {}
            for period in ("today", "week", "month", "all"):
                start = int(starts[period].timestamp() * 1000) if period in starts else 0
                selected = [e for e in events if start <= e["time"] <= now_ms]
                periods[period] = {key: sum(e[key] for e in selected) for key in TOKEN_FIELDS}
                periods[period]["calls"] = len(selected)
                grouped = {}
                for event in selected:
                    item = grouped.setdefault(event["model"], {"model": event["model"], "calls": 0, **dict.fromkeys(TOKEN_FIELDS, 0)})
                    for key in TOKEN_FIELDS:
                        item[key] += event[key]
                    item["calls"] += 1
                models[period] = sorted(grouped.values(), key=lambda m: m["tokens"], reverse=True)
            windows = [window_data(limits.get(key), key, observed, now_ms) for key in ("primary", "secondary")]
            data = {"provider": "codex", "connected": bool(events or limits or account),
                    "tokenBasis": "uncached_input_output",
                    "autoRefreshMinutes": minutes,
                    "user": {"email": account.get("email"), "plan": account.get("planType") or limits.get("planType") or limits.get("plan_type")},
                    "windows": windows, "periods": periods, "quotaUpdatedAt": observed or None,
                    "quotaSource": "account" if observed == remote_at and remote_at else "snapshot",
                    "syncing": self._remote_running, "syncError": self._error,
                    "usageTokens": {p: item["tokens"] for p, item in periods.items()},
                    "sessionCount": len({e["id"].split(":")[0] for e in events})}
            if not summary:
                target_year = int(year or now.year)
                if target_year < 1970 or target_year > 2100:
                    target_year = now.year
                data.update(models=models, events=summarize_turns(events)[:200],
                            heatmap=build_year_grid(target_year, aggregate_days_from_events(events)))
            return {"data": data, "updatedAt": now_ms}
