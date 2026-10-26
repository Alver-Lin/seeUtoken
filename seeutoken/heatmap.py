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


def aggregate_days_from_events(events: list[dict[str, Any]]) -> dict[str, dict[str, float | int]]:
    days: dict[str, dict[str, float | int]] = {}
    for e in events or []:
        key = day_key(e.get("time", 0))
        if not key:
            continue
        bucket = days.setdefault(key, {"cost": 0.0, "calls": 0})
        bucket["cost"] = float(bucket["cost"]) + float(e.get("cost") or 0)
        bucket["calls"] = int(bucket["calls"]) + 1
    for k, v in days.items():
        v["cost"] = round(float(v["cost"]), 2)
    return days


def level_for_cost(cost: float, max_cost: float) -> int:
    if not cost or cost <= 0:
        return 0
    if not max_cost or max_cost <= 0:
        return 1
    r = cost / max_cost
    if r <= 0.25:
        return 1
    if r <= 0.5:
        return 2
    if r <= 0.75:
        return 3
    return 4


def summarize_year(days: dict[str, dict[str, Any]], year: int) -> dict[str, Any]:
    prefix = f"{year}-"
    cost = 0.0
    calls = 0
    for k, v in (days or {}).items():
        if not k.startswith(prefix):
            continue
        cost += float(v.get("cost") or 0)
        calls += int(v.get("calls") or 0)
    return {"year": year, "cost": round(cost, 2), "calls": calls, "days": days}


def build_year_grid(year: int, days_map: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    try:
        year = int(year)
    except Exception:
        year = datetime.now().year
    if year < 1970 or year > 2100:
        year = datetime.now().year

    days = days_map or {}
    max_cost = 0.0
    prefix = f"{year}-"
    for k, v in days.items():
        if k.startswith(prefix):
            max_cost = max(max_cost, float(v.get("cost") or 0))

    months = []
    for month in range(1, 13):
        first_dow, days_in_month = calendar.monthrange(year, month)  # Mon=0..Sun=6
        # 转成 Sun=0..Sat=6
        start_dow = (first_dow + 1) % 7
        cells: list[dict[str, Any] | None] = [None] * start_dow
        for d in range(1, days_in_month + 1):
            key = f"{year}-{month:02d}-{d:02d}"
            hit = days.get(key)
            cost = float(hit["cost"]) if hit else 0.0
            calls = int(hit["calls"]) if hit else 0
            cells.append(
                {
                    "date": key,
                    "day": d,
                    "cost": cost,
                    "calls": calls,
                    "level": level_for_cost(cost, max_cost),
                }
            )
        while len(cells) % 7:
            cells.append(None)
        weeks = [cells[i : i + 7] for i in range(0, len(cells), 7)]
        months.append({"month": month, "weeks": weeks})

    summary = summarize_year(days, year)
    return {
        "year": year,
        "maxCost": max_cost,
        "months": months,
        "cost": summary["cost"],
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

    def add(m: int, d: int, cost: float, calls: int) -> None:
        days[f"{year}-{m:02d}-{d:02d}"] = {"cost": cost, "calls": calls}

    for d in range(1, 31):
        if d % 4 == 0:
            continue
        add(9, d, round(rnd() * 18 + (8 if d > 20 else 1), 2), int(rnd() * 12) + 1)
    for d in range(1, 27):
        if d % 5 == 0:
            continue
        add(10, d, round(rnd() * 22 + (10 if d < 15 else 2), 2), int(rnd() * 15) + 1)
    add(8, 28, 1.2, 2)
    add(8, 29, 0.8, 1)
    add(11, 2, 3.5, 4)
    return build_year_grid(year, days)
