"""按日聚合与年度热力图格子。"""

from __future__ import annotations

import calendar
from datetime import datetime
from typing import Any


def day_key(ts: int | float | str) -> str | None:
    try:
        if isinstance(ts, str) and ts.isdigit():
            ts = int(ts)
        dt = datetime.fromtimestamp(float(ts) / (1000 if float(ts) > 1e12 else 1))
    except Exception:
        return None
    return dt.strftime("%Y-%m-%d")


def _event_tokens(event: dict[str, Any]) -> int:
    return int(event.get("input") or 0) + int(event.get("output") or 0)


def aggregate_days_from_events(events: list[dict[str, Any]]) -> dict[str, dict[str, float | int]]:
    days: dict[str, dict[str, float | int]] = {}
    for e in events or []:
        key = day_key(e.get("time", 0))
        if not key:
            continue
        bucket = days.setdefault(key, {"tokens": 0, "calls": 0, "input": 0, "output": 0, "cache": 0})
        bucket["tokens"] = int(bucket["tokens"]) + _event_tokens(e)
        for field in ("input", "output", "cache"):
            bucket[field] += int(e.get(field) or 0)
        bucket["calls"] = int(bucket["calls"]) + 1
    return days


def level_for_tokens(tokens: float | int, max_tokens: float | int) -> int:
    tokens = float(tokens or 0)
    max_tokens = float(max_tokens or 0)
    if not tokens or tokens <= 0:
        return 0
    if not max_tokens or max_tokens <= 0:
        return 1
    r = tokens / max_tokens
    if r <= 0.25:
        return 1
    if r <= 0.5:
        return 2
    if r <= 0.75:
        return 3
    return 4


def summarize_year(days: dict[str, dict[str, Any]], year: int) -> dict[str, Any]:
    prefix = f"{year}-"
    tokens = 0
    calls = 0
    for k, v in (days or {}).items():
        if not k.startswith(prefix):
            continue
        tokens += int(v.get("tokens") or 0)
        calls += int(v.get("calls") or 0)
    return {"year": year, "tokens": tokens, "calls": calls, "days": days}


def build_year_grid(year: int, days_map: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    try:
        year = int(year)
    except Exception:
        year = datetime.now().year
    if year < 1970 or year > 2100:
        year = datetime.now().year

    days = days_map or {}
    max_tokens = 0
    prefix = f"{year}-"
    for k, v in days.items():
        if k.startswith(prefix):
            max_tokens = max(max_tokens, int(v.get("tokens") or 0))

    months = []
    for month in range(1, 13):
        first_dow, days_in_month = calendar.monthrange(year, month)  # Mon=0..Sun=6
        # 转成 Sun=0..Sat=6
        start_dow = (first_dow + 1) % 7
        cells: list[dict[str, Any] | None] = [None] * start_dow
        for d in range(1, days_in_month + 1):
            key = f"{year}-{month:02d}-{d:02d}"
            hit = days.get(key)
            tokens = int(hit["tokens"]) if hit else 0
            calls = int(hit["calls"]) if hit else 0
            cells.append(
                {
                    "date": key,
                    "day": d,
                    "tokens": tokens,
                    "calls": calls,
                    "level": level_for_tokens(tokens, max_tokens),
                }
            )
        while len(cells) % 7:
            cells.append(None)
        weeks = [cells[i : i + 7] for i in range(0, len(cells), 7)]
        months.append({"month": month, "weeks": weeks})

    summary = summarize_year(days, year)
    return {
        "year": year,
        "maxTokens": max_tokens,
        "months": months,
        "tokens": summary["tokens"],
        "calls": summary["calls"],
        "days": days,
    }


def get_demo_heatmap(year: int | None = None) -> dict[str, Any]:
    try:
        year = int(year) if year is not None else datetime.now().year
    except Exception:
        year = datetime.now().year
    if year < 1970 or year > 2100:
        year = datetime.now().year
    days: dict[str, dict[str, float | int]] = {}
    seed = year * 997

    def rnd() -> float:
        nonlocal seed
        seed = (seed * 16807) % 2147483647
        return (seed - 1) / 2147483646

    def add(m: int, d: int, tokens: int, calls: int) -> None:
        days[f"{year}-{m:02d}-{d:02d}"] = {"tokens": tokens, "calls": calls}

    for d in range(1, 31):
        if d % 4 == 0:
            continue
        add(9, d, int(rnd() * 180_000 + (80_000 if d > 20 else 10_000)), int(rnd() * 12) + 1)
    for d in range(1, 27):
        if d % 5 == 0:
            continue
        add(10, d, int(rnd() * 220_000 + (100_000 if d < 15 else 20_000)), int(rnd() * 15) + 1)
    add(8, 28, 12_000, 2)
    add(8, 29, 8_000, 1)
    add(11, 2, 35_000, 4)
    return build_year_grid(year, days)
