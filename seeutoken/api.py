"""Cursor Dashboard 用量 API。"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any
from urllib.parse import quote

import requests

from .auth import resolve_session_token
from .demo import get_demo_data
from .heatmap import aggregate_days_from_events, build_year_grid, get_demo_heatmap

BASE = "https://cursor.com"
_heatmap_cache: dict[str, dict[str, Any]] = {}


class ApiError(Exception):
    def __init__(self, message: str, code: str = "ERROR", status: int | None = None):
        super().__init__(message)
        self.code = code
        self.status = status


def _api_fetch(
    path: str,
    *,
    cookie: str,
    method: str = "GET",
    body: dict | None = None,
) -> Any:
    headers = {
        "Accept": "application/json",
        "Cookie": f"WorkosCursorSessionToken={quote(cookie, safe='')}",
        "User-Agent": "seeUtoken/1.0",
    }
    if method != "GET":
        headers["Content-Type"] = "application/json"
        headers["Origin"] = BASE
        headers["Referer"] = f"{BASE}/dashboard"

    res = requests.request(
        method,
        f"{BASE}{path}",
        headers=headers,
        json=body if method != "GET" else None,
        timeout=30,
    )
    if res.status_code in (401, 403):
        raise ApiError("登录已过期，请重新登录 Cursor 或粘贴新的 Session Token", "AUTH_EXPIRED", res.status_code)
    if not res.ok:
        raise ApiError(f"API {res.status_code}: {res.text[:120]}", "API_ERROR", res.status_code)
    if res.status_code == 204:
        return None
    ct = res.headers.get("content-type", "")
    if "json" not in ct:
        return None
    return res.json()


def _dollars(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _parse_ms(value: Any, fallback: int | None = None) -> int:
    """把 ISO / 毫秒 / 秒时间戳统一成毫秒；失败时返回 fallback。"""
    if value is None or value == "":
        if fallback is None:
            raise ValueError("empty timestamp")
        return fallback
    if isinstance(value, (int, float)):
        n = float(value)
        return int(n if n > 1e12 else n * 1000)
    text = str(value).strip()
    if text.isdigit() or (text.startswith("-") and text[1:].isdigit()):
        n = float(text)
        return int(n if abs(n) > 1e12 else n * 1000)
    try:
        cleaned = text.replace("Z", "+00:00")
        return int(datetime.fromisoformat(cleaned).timestamp() * 1000)
    except Exception:
        if fallback is None:
            raise
        return fallback


def _safe_year(year: Any) -> int:
    try:
        y = int(year)
    except Exception:
        y = datetime.now().year
    if y < 1970 or y > 2100:
        return datetime.now().year
    return y


def _summarize_agg(agg: dict | None) -> dict[str, Any]:
    if not agg:
        return {"cost": 0, "calls": 0, "input": 0, "output": 0, "cache": 0}
    items = agg.get("aggregations") or agg.get("items") or []
    if agg.get("totalCents") is not None:
        cost_cents = float(agg["totalCents"])
    else:
        cost_cents = sum(float(i.get("totalCents") or 0) for i in items)
    if agg.get("totalCalls") is not None or agg.get("numRequests") is not None:
        calls = float(agg.get("totalCalls") if agg.get("totalCalls") is not None else agg.get("numRequests"))
    else:
        calls = sum(float(i.get("numRequests") or i.get("requests") or i.get("count") or 0) for i in items)
    return {
        "cost": cost_cents / 100,
        "calls": int(calls),
        "input": sum(int(i.get("inputTokens") or 0) for i in items),
        "output": sum(int(i.get("outputTokens") or 0) for i in items),
        "cache": sum(int(i.get("cacheReadTokens") or 0) + int(i.get("cacheWriteTokens") or 0) for i in items),
    }


def _models_from_agg(agg: dict | None) -> list[dict[str, Any]]:
    items = (agg or {}).get("aggregations") or (agg or {}).get("items") or []
    total = sum(float(i.get("totalCents") or 0) for i in items) or 1
    out = []
    for item in items:
        cents = float(item.get("totalCents") or 0)
        out.append(
            {
                "model": item.get("model") or item.get("modelName") or "unknown",
                "cost": cents / 100,
                "percent": (cents / total) * 100,
                "calls": int(item.get("numRequests") or item.get("requests") or item.get("count") or 0),
                "input": int(item.get("inputTokens") or 0),
                "output": int(item.get("outputTokens") or 0),
                "cache": int(item.get("cacheReadTokens") or 0) + int(item.get("cacheWriteTokens") or 0),
            }
        )
    out.sort(key=lambda x: x["cost"], reverse=True)
    return out


def _normalize_events(payload: dict | None) -> list[dict[str, Any]]:
    items = (payload or {}).get("usageEventsDisplay") or (payload or {}).get("events") or []
    out = []
    for e in items:
        tu = e.get("tokenUsage") or {}
        cost_cents = float(
            e["chargedCents"]
            if e.get("chargedCents") is not None
            else tu.get("totalCents")
            if tu.get("totalCents") is not None
            else e.get("requestsCosts") or 0
        )
        ts = e.get("timestamp")
        try:
            time_ms = int(ts)
        except Exception:
            try:
                time_ms = int(datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp() * 1000)
            except Exception:
                time_ms = 0
        out.append(
            {
                "time": time_ms,
                "model": e.get("model") or "—",
                "kind": e.get("kind") or "",
                "cost": cost_cents / 100,
                "input": int(tu.get("inputTokens") or 0),
                "output": int(tu.get("outputTokens") or 0),
                "cache": int(tu.get("cacheReadTokens") or 0) + int(tu.get("cacheWriteTokens") or 0),
            }
        )
    return out


def _fetch_all_events(cookie: str, user_id: Any, start_ms: int, end_ms: int) -> list[dict[str, Any]]:
    all_events: list[dict[str, Any]] = []
    page = 1
    page_size = 200
    total = float("inf")
    while len(all_events) < total and page <= 40:
        res = _api_fetch(
            "/api/dashboard/get-filtered-usage-events",
            cookie=cookie,
            method="POST",
            body={
                "teamId": 0,
                "startDate": str(start_ms),
                "endDate": str(end_ms),
                "userId": user_id,
                "page": page,
                "pageSize": page_size,
            },
        )
        batch = _normalize_events(res)
        total = float(res.get("totalUsageEventsCount", len(all_events) + len(batch))) if res else len(all_events)
        all_events.extend(batch)
        if not batch or len(batch) < page_size:
            break
        page += 1
    return all_events


def fetch_heatmap_for_year(year: int, manual_token: str | None = None, force: bool = False) -> dict[str, Any]:
    year = _safe_year(year)
    key = str(year)
    if not force and key in _heatmap_cache:
        return _heatmap_cache[key]

    auth = resolve_session_token(manual_token)
    if not auth.get("cookie"):
        demo = get_demo_heatmap(year)
        _heatmap_cache[key] = demo
        return demo

    me = _api_fetch("/api/auth/me", cookie=auth["cookie"])
    user_id = (me or {}).get("id")
    if not user_id:
        demo = get_demo_heatmap(year)
        _heatmap_cache[key] = demo
        return demo

    start_ms = int(datetime(year, 1, 1).timestamp() * 1000)
    end_ms = min(int(time.time() * 1000), int(datetime(year, 12, 31, 23, 59, 59).timestamp() * 1000))
    events = _fetch_all_events(auth["cookie"], user_id, start_ms, end_ms)
    grid = build_year_grid(year, aggregate_days_from_events(events))
    _heatmap_cache[key] = grid
    return grid


def clear_heatmap_cache() -> None:
    _heatmap_cache.clear()


def fetch_all_usage_data(manual_token: str | None = None) -> dict[str, Any]:
    auth = resolve_session_token(manual_token)
    if not auth.get("cookie"):
        raise ApiError("未找到 Cursor 登录凭证（请先登录 Cursor IDE，或手动填写 Token）", "NO_SESSION")

    cookie = auth["cookie"]
    me = _api_fetch("/api/auth/me", cookie=cookie)
    if not me or (not me.get("id") and not me.get("email")):
        raise ApiError("无法获取账号信息，凭证可能已失效", "AUTH_EXPIRED")

    user_id = me["id"]
    now = int(time.time() * 1000)

    usage = summary = period = None
    try:
        usage = _api_fetch(f"/api/usage?user={quote(str(user_id))}", cookie=cookie)
    except Exception:
        pass
    try:
        summary = _api_fetch("/api/usage-summary", cookie=cookie)
    except Exception:
        pass
    try:
        period = _api_fetch("/api/dashboard/get-current-period-usage", cookie=cookie, method="POST", body={})
    except Exception:
        pass

    month_fallback = int(
        datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000
    )
    start_of_month = (
        (usage or {}).get("startOfMonth")
        or (summary or {}).get("startOfMonth")
        or (period or {}).get("billingCycleStart")
        or month_fallback
    )
    cycle_start = _parse_ms(start_of_month, month_fallback)
    if (period or {}).get("billingCycleEnd"):
        cycle_end = _parse_ms(period["billingCycleEnd"], cycle_start + 30 * 86_400_000)
    else:
        cycle_end = cycle_start + 30 * 86_400_000

    day_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    weekday = day_start.isoweekday()  # Mon=1
    week_start = day_start.timestamp() * 1000 - (weekday - 1) * 86_400_000
    month_start = float(month_fallback)

    def post_agg(start: float):
        try:
            return _api_fetch(
                "/api/dashboard/get-aggregated-usage-events",
                cookie=cookie,
                method="POST",
                body={
                    "teamId": 0,
                    "startDate": str(int(start)),
                    "endDate": str(now),
                    "userId": user_id,
                },
            )
        except Exception:
            return None

    agg_cycle = post_agg(cycle_start)
    agg_today = post_agg(day_start.timestamp() * 1000)
    agg_week = post_agg(week_start)
    agg_month = post_agg(month_start)

    try:
        events = _api_fetch(
            "/api/dashboard/get-filtered-usage-events",
            cookie=cookie,
            method="POST",
            body={
                "teamId": 0,
                "startDate": str(cycle_start),
                "endDate": str(now),
                "userId": user_id,
                "page": 1,
                "pageSize": 50,
            },
        )
    except Exception:
        events = None

    plan = ((summary or {}).get("individualUsage") or {}).get("plan") or (summary or {}).get("plan") or {}
    plan_usage = (period or {}).get("planUsage") or (period or {}).get("usage") or {}

    total_limit = _dollars(
        plan_usage.get("limit")
        or plan_usage.get("includedSpendLimit")
        or plan.get("limit")
        or plan.get("totalLimit")
    ) or 0
    used_spend = _dollars(
        plan_usage.get("totalSpend")
        or plan_usage.get("spend")
        or plan_usage.get("used")
        or plan.get("used")
        or _summarize_agg(agg_cycle)["cost"]
    )
    if used_spend is None:
        used_spend = _summarize_agg(agg_cycle)["cost"]

    remaining = _dollars(plan_usage.get("remaining") or plan.get("remaining"))
    if remaining is None and total_limit > 0:
        remaining = max(0.0, total_limit - used_spend)
    if remaining is None:
        remaining = 0.0

    total_quota = total_limit
    if not total_quota and used_spend + remaining > 0:
        total_quota = used_spend + remaining

    gifted = _dollars(plan_usage.get("bonus") or plan.get("bonus") or plan_usage.get("gifted")) or 0
    auto_percent = float(
        (period or {}).get("autoPercentUsed")
        or (summary or {}).get("autoPercentUsed")
        or plan_usage.get("autoPercentUsed")
        or 0
    )
    api_percent = float(
        (period or {}).get("apiPercentUsed")
        or (summary or {}).get("apiPercentUsed")
        or plan_usage.get("apiPercentUsed")
        or 0
    )
    membership = (
        me.get("membershipType")
        or (summary or {}).get("membershipType")
        or plan.get("membershipType")
        or plan.get("name")
        or "Pro"
    )

    used_percent = min(100, (used_spend / total_quota) * 100) if total_quota > 0 else auto_percent
    remaining_percent = (
        max(0, 100 - min(100, (used_spend / total_quota) * 100)) if total_quota > 0 else max(0, 100 - auto_percent)
    )

    return {
        "fetchedAt": now,
        "authSource": auth.get("source"),
        "user": {
            "id": user_id,
            "email": me.get("email") or "",
            "name": me.get("name") or "",
            "membership": str(membership),
        },
        "cycle": {"start": cycle_start, "end": cycle_end, "resetAt": cycle_end},
        "quota": {
            "total": total_quota,
            "used": used_spend,
            "remaining": remaining,
            "gifted": gifted,
            "usedPercent": used_percent,
            "remainingPercent": remaining_percent,
        },
        "limits": {"cursorModelsPercent": auto_percent, "otherModelsPercent": api_percent},
        "periods": {
            "today": _summarize_agg(agg_today),
            "week": _summarize_agg(agg_week),
            "month": _summarize_agg(agg_month),
            "cycle": _summarize_agg(agg_cycle),
            "all": _summarize_agg(agg_cycle),
        },
        "models": {
            "today": _models_from_agg(agg_today),
            "week": _models_from_agg(agg_week),
            "month": _models_from_agg(agg_month),
            "cycle": _models_from_agg(agg_cycle),
            "all": _models_from_agg(agg_cycle),
        },
        "events": _normalize_events(events),
        "heatmap": None,
        "raw": {"usage": usage, "summary": summary, "period": period},
    }


def load_usage(
    *,
    manual_token: str | None = None,
    use_demo_when_logged_out: bool = True,
) -> dict[str, Any]:
    try:
        clear_heatmap_cache()
        data = fetch_all_usage_data(manual_token)
        year = datetime.now().year
        try:
            data["heatmap"] = fetch_heatmap_for_year(year, manual_token=manual_token, force=True)
        except Exception:
            data["heatmap"] = get_demo_heatmap(year)
        return {"data": data, "error": None, "updatedAt": int(time.time() * 1000)}
    except ApiError as exc:
        if use_demo_when_logged_out and exc.code in ("NO_SESSION", "AUTH_EXPIRED"):
            return {
                "data": get_demo_data(),
                "error": {"code": exc.code, "message": str(exc)},
                "updatedAt": int(time.time() * 1000),
            }
        raise
