"""Cursor Dashboard 用量 API。"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .auth import extract_jwt, resolve_session_token
from .demo import get_demo_data
from .heatmap import aggregate_days_from_events, build_year_grid, get_demo_heatmap
from .projects import conversation_project_map, resolve_project_name

BASE = "https://cursor.com"
API2 = "https://api2.cursor.sh"
_heatmap_cache: dict[str, dict[str, Any]] = {}
_SESSION: requests.Session | None = None
_REQUEST_TIMEOUT = 12


class ApiError(Exception):
    def __init__(self, message: str, code: str = "ERROR", status: int | None = None):
        super().__init__(message)
        self.code = code
        self.status = status


def _session() -> requests.Session:
    global _SESSION
    if _SESSION is None:
        s = requests.Session()
        retry = Retry(total=1, backoff_factor=0.2, status_forcelist=(502, 503, 504))
        adapter = HTTPAdapter(pool_connections=12, pool_maxsize=12, max_retries=retry)
        s.mount("https://", adapter)
        s.mount("http://", adapter)
        _SESSION = s
    return _SESSION


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

    res = _session().request(
        method,
        f"{BASE}{path}",
        headers=headers,
        json=body if method != "GET" else None,
        timeout=_REQUEST_TIMEOUT,
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


def _safe_fetch(*args, **kwargs) -> Any:
    try:
        return _api_fetch(*args, **kwargs)
    except Exception:
        return None


def _api2_period_usage(jwt: str | None) -> dict | None:
    """个人版官方额度：api2 DashboardService/GetCurrentPeriodUsage。"""
    if not jwt:
        return None
    try:
        res = _session().post(
            f"{API2}/aiserver.v1.DashboardService/GetCurrentPeriodUsage",
            headers={
                "Authorization": f"Bearer {jwt}",
                "Content-Type": "application/json",
                "Connect-Protocol-Version": "1",
                "User-Agent": "seeUtoken/1.0",
                "Accept": "application/json",
            },
            json={},
            timeout=_REQUEST_TIMEOUT,
        )
        if res.status_code in (401, 403) or not res.ok:
            return None
        data = res.json()
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _dollars(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _cents_to_dollars(v: Any) -> float | None:
    """Cursor planUsage / individualUsage.plan 金额字段与 totalCents 同单位（美分）。"""
    raw = _dollars(v)
    if raw is None:
        return None
    return raw / 100.0


def _as_int(v: Any) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


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
        return _empty_period()
    items = agg.get("aggregations") or agg.get("items") or []
    if agg.get("totalCostCents") is not None:
        cost_cents = float(agg["totalCostCents"])
    elif agg.get("totalCents") is not None:
        cost_cents = float(agg["totalCents"])
    else:
        cost_cents = sum(float(i.get("totalCents") or 0) for i in items)

    calls = None
    if agg.get("totalCalls") is not None:
        calls = _as_int(agg.get("totalCalls"))
    elif agg.get("numRequests") is not None:
        calls = _as_int(agg.get("numRequests"))
    else:
        call_vals = []
        for i in items:
            if i.get("numRequests") is not None:
                call_vals.append(i.get("numRequests"))
            elif i.get("requests") is not None:
                call_vals.append(i.get("requests"))
            elif i.get("count") is not None:
                call_vals.append(i.get("count"))
        if call_vals:
            calls = sum(_as_int(v) for v in call_vals)

    if agg.get("totalInputTokens") is not None:
        input_tokens = _as_int(agg.get("totalInputTokens"))
        output_tokens = _as_int(agg.get("totalOutputTokens"))
        cache_tokens = _as_int(agg.get("totalCacheReadTokens")) + _as_int(agg.get("totalCacheWriteTokens"))
    else:
        input_tokens = sum(_as_int(i.get("inputTokens")) for i in items)
        output_tokens = sum(_as_int(i.get("outputTokens")) for i in items)
        cache_tokens = sum(
            _as_int(i.get("cacheReadTokens")) + _as_int(i.get("cacheWriteTokens")) for i in items
        )

    return {
        "cost": cost_cents / 100,
        "calls": calls,
        "input": input_tokens,
        "output": output_tokens,
        "cache": cache_tokens,
        "tokens": input_tokens + output_tokens,
        "processedTokens": input_tokens + output_tokens + cache_tokens,
    }


def _model_display_name(raw: Any) -> str:
    name = str(raw or "").strip() or "unknown"
    if name.lower() == "default":
        return "auto"
    return name


def _model_pool(name: str, auto_bucket: set[str] | None) -> str:
    """归类到 Cursor 模型池（Auto）或其余模型池（API）。"""
    raw = str(name or "").strip().lower()
    key = "default" if raw in ("auto", "default", "") else raw
    bucket = auto_bucket or set()
    if key in bucket or raw in bucket:
        return "cursor"
    # 常见 Cursor 托管模型前缀兜底
    if key.startswith(("composer-", "cursor-grok-", "grok-4.", "vega")):
        return "cursor"
    return "other"


def _models_from_agg(agg: dict | None, auto_bucket: set[str] | None = None) -> list[dict[str, Any]]:
    items = (agg or {}).get("aggregations") or (agg or {}).get("items") or []
    # Cursor 会把同一 modelIntent（如 default/auto）按 tier 拆成多行，展示名合并
    merged: dict[str, dict[str, Any]] = {}
    for item in items:
        cents = float(item.get("totalCents") or 0)
        req = item.get("numRequests")
        if req is None:
            req = item.get("requests")
        if req is None:
            req = item.get("count")
        inp = _as_int(item.get("inputTokens"))
        out_tok = _as_int(item.get("outputTokens"))
        cache = _as_int(item.get("cacheReadTokens")) + _as_int(item.get("cacheWriteTokens"))
        model = _model_display_name(
            item.get("modelIntent") or item.get("model") or item.get("modelName")
        )
        row = merged.get(model)
        if row is None:
            merged[model] = {
                "model": model,
                "pool": _model_pool(model, auto_bucket),
                "cost": cents / 100,
                "tokens": inp + out_tok,
                "processedTokens": inp + out_tok + cache,
                "calls": _as_int(req) if req is not None else None,
                "input": inp,
                "output": out_tok,
                "cache": cache,
            }
        else:
            row["cost"] += cents / 100
            row["input"] += inp
            row["output"] += out_tok
            row["cache"] += cache
            row["tokens"] = row["input"] + row["output"]
            row["processedTokens"] = row["tokens"] + row["cache"]
            if req is not None:
                row["calls"] = (row["calls"] or 0) + _as_int(req)

    rows = list(merged.values())
    token_total = sum(r["tokens"] for r in rows) or 1
    cost_total = sum(r["cost"] for r in rows) or 1.0
    for r in rows:
        r["percent"] = (r["tokens"] / token_total) * 100
        r["costPercent"] = (r["cost"] / cost_total) * 100
    rows.sort(key=lambda x: x["tokens"], reverse=True)
    return rows


def _normalize_events(payload: dict | None) -> list[dict[str, Any]]:
    items = (payload or {}).get("usageEventsDisplay") or (payload or {}).get("events") or []
    project_map = conversation_project_map()
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
        cid = e.get("conversationId") or e.get("composerId") or ""
        project = resolve_project_name(cid, project_map)
        out.append(
            {
                "time": time_ms,
                "model": _model_display_name(e.get("modelIntent") or e.get("model")) if (e.get("modelIntent") or e.get("model")) else "—",
                "kind": e.get("kind") or "",
                "project": project or "—",
                "conversationId": cid or "",
                "cost": cost_cents / 100,
                "input": int(tu.get("inputTokens") or 0),
                "output": int(tu.get("outputTokens") or 0),
                "cache": int(tu.get("cacheReadTokens") or 0) + int(tu.get("cacheWriteTokens") or 0),
                "tokens": int(tu.get("inputTokens") or 0) + int(tu.get("outputTokens") or 0),
                "processedTokens": sum(int(tu.get(k) or 0) for k in (
                    "inputTokens", "outputTokens", "cacheReadTokens", "cacheWriteTokens")),
            }
        )
    return out


def _fetch_all_events(
    cookie: str,
    user_id: Any,
    start_ms: int,
    end_ms: int,
    *,
    page_size: int = 500,
    max_pages: int = 12,
) -> list[dict[str, Any]]:
    """分页拉取事件。热力图后台用，限制页数避免拖垮首屏。"""
    all_events: list[dict[str, Any]] = []
    page = 1
    total = float("inf")
    while len(all_events) < total and page <= max_pages:
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


def fetch_heatmap_for_year(
    year: int,
    manual_token: str | None = None,
    force: bool = False,
    *,
    user_id: Any = None,
    cookie: str | None = None,
) -> dict[str, Any]:
    year = _safe_year(year)
    key = str(year)
    if not force and key in _heatmap_cache:
        return _heatmap_cache[key]

    auth_cookie = cookie
    auth_user = user_id
    if not auth_cookie:
        auth = resolve_session_token(manual_token)
        auth_cookie = auth.get("cookie")
    if not auth_cookie:
        demo = get_demo_heatmap(year)
        _heatmap_cache[key] = demo
        return demo

    if not auth_user:
        me = _safe_fetch("/api/auth/me", cookie=auth_cookie)
        auth_user = (me or {}).get("id")
    if not auth_user:
        demo = get_demo_heatmap(year)
        _heatmap_cache[key] = demo
        return demo

    start_ms = int(datetime(year, 1, 1).timestamp() * 1000)
    end_ms = min(int(time.time() * 1000), int(datetime(year, 12, 31, 23, 59, 59).timestamp() * 1000))
    events = _fetch_all_events(auth_cookie, auth_user, start_ms, end_ms)
    grid = build_year_grid(year, aggregate_days_from_events(events))
    _heatmap_cache[key] = grid
    return grid


def clear_heatmap_cache() -> None:
    _heatmap_cache.clear()


def _empty_period() -> dict[str, Any]:
    return {"cost": 0, "calls": None, "input": 0, "output": 0, "cache": 0,
            "tokens": 0, "processedTokens": 0}


def _membership_label(stripe: dict | None, me: dict, summary: dict | None, plan: dict) -> str:
    """对齐 usage-tracker detectTier / planLabel。"""
    if isinstance(stripe, dict):
        if stripe.get("isTeamMember"):
            return "Team"
        raw = (
            stripe.get("individualMembershipType")
            or stripe.get("membershipType")
            or ""
        )
        m = str(raw).lower()
        if m == "ultra":
            return "Ultra"
        if m in ("pro_plus", "pro+"):
            return "Pro+"
        if m == "pro":
            return "Pro"
        if m in ("free", ""):
            # 可能无 stripe.membership，继续向下兜底
            pass
        elif raw:
            return str(raw)

    fallback = (
        me.get("membershipType")
        or (summary or {}).get("membershipType")
        or plan.get("membershipType")
        or plan.get("name")
        or "Pro"
    )
    return str(fallback)


def _compose_usage_data(
    *,
    auth: dict[str, Any],
    me: dict[str, Any],
    summary: dict | None,
    period: dict | None,
    usage: dict | None,
    now: int,
    stripe: dict | None = None,
    agg_today=None,
    agg_week=None,
    agg_month=None,
    agg_cycle=None,
    agg_all=None,
    events=None,
    partial: bool = False,
) -> dict[str, Any]:
    user_id = me.get("id")
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

    plan = ((summary or {}).get("individualUsage") or {}).get("plan") or (summary or {}).get("plan") or {}
    plan_usage = (period or {}).get("planUsage") or (period or {}).get("usage") or {}
    if not isinstance(plan_usage, dict):
        plan_usage = {}
    breakdown = plan.get("breakdown") if isinstance(plan.get("breakdown"), dict) else {}

    # —— 个人版额度：套餐内 + 赠送合计展示 ——
    # 金额单位美分。官网 Spending 只标 $20 套餐内；本应用把赠送折进总量/剩余。
    def _pct(v: Any) -> float | None:
        try:
            if v is None or v == "":
                return None
            n = float(v)
            return n if n == n else None
        except (TypeError, ValueError):
            return None

    def _cents_field(*candidates: Any) -> float | None:
        for src in candidates:
            if src is None:
                continue
            try:
                return float(src)
            except (TypeError, ValueError):
                continue
        return None

    limit_cents = _cents_field(plan_usage.get("limit"), plan.get("limit"), breakdown.get("included"))
    remaining_cents = _cents_field(plan_usage.get("remaining"), plan.get("remaining"))
    included_spend_cents = _cents_field(
        plan_usage.get("includedSpend"),
        plan.get("used"),
        plan_usage.get("used"),
    )
    bonus_cents = _cents_field(
        plan_usage.get("bonusSpend"),
        breakdown.get("bonus"),
        plan.get("bonus"),
    )
    total_spend_cents = _cents_field(
        plan_usage.get("totalSpend"),
        breakdown.get("total"),
    )

    total_pct = _pct(
        plan_usage.get("totalPercentUsed")
        if plan_usage.get("totalPercentUsed") is not None
        else plan.get("totalPercentUsed")
        if plan.get("totalPercentUsed") is not None
        else (period or {}).get("totalPercentUsed")
    )
    auto_percent = _pct(
        plan_usage.get("autoPercentUsed")
        if plan_usage.get("autoPercentUsed") is not None
        else plan.get("autoPercentUsed")
        if plan.get("autoPercentUsed") is not None
        else (period or {}).get("autoPercentUsed")
    ) or 0.0
    api_percent = _pct(
        plan_usage.get("apiPercentUsed")
        if plan_usage.get("apiPercentUsed") is not None
        else plan.get("apiPercentUsed")
        if plan.get("apiPercentUsed") is not None
        else (period or {}).get("apiPercentUsed")
    ) or 0.0

    included_limit = _cents_to_dollars(limit_cents) or 0.0
    gifted = _cents_to_dollars(bonus_cents) or 0.0

    if included_spend_cents is not None:
        included_used = _cents_to_dollars(included_spend_cents) or 0.0
    elif remaining_cents is not None and limit_cents is not None:
        included_used = _cents_to_dollars(float(limit_cents) - float(remaining_cents)) or 0.0
    else:
        included_used = 0.0

    included_remaining = (
        _cents_to_dollars(remaining_cents)
        if remaining_cents is not None
        else max(0.0, included_limit - included_used)
    )
    if included_remaining is None:
        included_remaining = 0.0

    # 本周期实际总花费（套餐内 + 赠送已用）
    if total_spend_cents is not None:
        used_spend = _cents_to_dollars(total_spend_cents) or 0.0
    else:
        used_spend = included_used + gifted

    # 有 totalPercentUsed：按「已用 / 百分比」反推含赠送的有效总额，使剩余与官网%一致
    display_pct = total_pct if total_pct is not None and total_pct > 0 else None
    if display_pct is None and auto_percent > 0.5:
        display_pct = auto_percent

    if display_pct and display_pct > 0 and used_spend > 0:
        total_quota = used_spend / (min(display_pct, 100.0) / 100.0)
        remaining = max(0.0, total_quota - used_spend)
        used_percent = min(100.0, max(0.0, display_pct))
        remaining_percent = max(0.0, 100.0 - used_percent)
    else:
        # 无百分比时：总量 = 套餐额度 + 赠送已用（至少能反映「+赠送」）
        total_quota = included_limit + gifted
        if total_quota <= 0:
            total_quota = used_spend
        remaining = max(0.0, total_quota - used_spend)
        if total_quota > 0:
            used_percent = min(100.0, max(0.0, (used_spend / total_quota) * 100))
            remaining_percent = min(100.0, max(0.0, (remaining / total_quota) * 100))
        else:
            used_percent = 0.0
            remaining_percent = 0.0

    membership = _membership_label(stripe, me, summary, plan)

    auto_bucket_list = (period or {}).get("autoBucketModels") or []
    if not isinstance(auto_bucket_list, list):
        auto_bucket_list = []
    auto_bucket = {str(x).strip().lower() for x in auto_bucket_list if x}

    empty = _empty_period()
    return {
        "fetchedAt": now,
        "tokenBasis": "uncached_input_output",
        "partial": partial,
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
            "included": included_limit,
            "includedUsed": included_used,
            "includedRemaining": included_remaining,
            "usedPercent": used_percent,
            "remainingPercent": remaining_percent,
            "autoPercent": auto_percent,
            "apiPercent": api_percent,
            "cursorModelsPercent": auto_percent,
            "otherModelsPercent": api_percent,
        },
        "limits": {
            "cursorModelsPercent": auto_percent,
            "otherModelsPercent": api_percent,
            "autoBucketModels": sorted(auto_bucket),
        },
        "periods": {
            "today": _summarize_agg(agg_today) if agg_today is not None else empty,
            "week": _summarize_agg(agg_week) if agg_week is not None else empty,
            "month": _summarize_agg(agg_month) if agg_month is not None else empty,
            "cycle": _summarize_agg(agg_cycle) if agg_cycle is not None else empty,
            # 「全部」必须用独立聚合，禁止静默退化成 cycle（否则与「本周期」完全相同）
            "all": _summarize_agg(agg_all) if agg_all is not None else empty,
        },
        "models": {
            "today": _models_from_agg(agg_today, auto_bucket) if agg_today is not None else [],
            "week": _models_from_agg(agg_week, auto_bucket) if agg_week is not None else [],
            "month": _models_from_agg(agg_month, auto_bucket) if agg_month is not None else [],
            "cycle": _models_from_agg(agg_cycle, auto_bucket) if agg_cycle is not None else [],
            "all": _models_from_agg(agg_all, auto_bucket) if agg_all is not None else [],
        },
        "events": _normalize_events(events) if events is not None else [],
        "heatmap": None,
        "raw": {"usage": usage, "summary": summary, "period": period, "stripe": stripe},
        "_authCookie": auth.get("cookie"),
        "_cycleStart": cycle_start,
    }


def fetch_usage_fast(manual_token: str | None = None) -> dict[str, Any]:
    """首屏快路径：账号 + 个人版额度（优先 api2 GetCurrentPeriodUsage）。"""
    auth = resolve_session_token(manual_token)
    if not auth.get("cookie"):
        raise ApiError("未找到 Cursor 登录凭证（请先登录 Cursor IDE，或手动填写 Token）", "NO_SESSION")

    cookie = auth["cookie"]
    jwt = auth.get("jwt") or extract_jwt(cookie)
    now = int(time.time() * 1000)
    with ThreadPoolExecutor(max_workers=4) as pool:
        f_me = pool.submit(_api_fetch, "/api/auth/me", cookie=cookie)
        f_summary = pool.submit(_safe_fetch, "/api/usage-summary", cookie=cookie)
        f_stripe = pool.submit(_safe_fetch, "/api/auth/stripe", cookie=cookie)
        f_api2 = pool.submit(_api2_period_usage, jwt)
        f_period_web = pool.submit(
            _safe_fetch,
            "/api/dashboard/get-current-period-usage",
            cookie=cookie,
            method="POST",
            body={},
        )
        me = f_me.result()
        summary = f_summary.result()
        stripe = f_stripe.result()
        period = f_api2.result() or f_period_web.result()

    if not me or (not me.get("id") and not me.get("email")):
        raise ApiError("无法获取账号信息，凭证可能已失效", "AUTH_EXPIRED")

    return _compose_usage_data(
        auth=auth,
        me=me,
        summary=summary,
        period=period,
        usage=None,
        stripe=stripe if isinstance(stripe, dict) else None,
        now=now,
        partial=True,
    )


def enrich_usage_details(data: dict[str, Any]) -> dict[str, Any]:
    """补齐模型分布、分时段统计、最近事件。"""
    cookie = data.get("_authCookie")
    user_id = (data.get("user") or {}).get("id")
    if not cookie or not user_id:
        out = {k: v for k, v in data.items() if not str(k).startswith("_")}
        out["partial"] = False
        return out

    now = int(time.time() * 1000)
    cycle_start = int(data.get("_cycleStart") or now)
    day_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    weekday = day_start.isoweekday()
    week_start = day_start.timestamp() * 1000 - (weekday - 1) * 86_400_000
    month_start = float(
        int(datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)
    )
    # Cursor 聚合接口对过长回溯常失败；当年 1 月 1 日可稳定返回「全部」量级数据
    all_start = float(
        int(datetime.now().replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)
    )

    def post_agg(start: float):
        return _safe_fetch(
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

    with ThreadPoolExecutor(max_workers=7) as pool:
        futures = {
            pool.submit(post_agg, cycle_start): "cycle",
            pool.submit(post_agg, day_start.timestamp() * 1000): "today",
            pool.submit(post_agg, week_start): "week",
            pool.submit(post_agg, month_start): "month",
            pool.submit(post_agg, all_start): "all",
            pool.submit(
                _safe_fetch,
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
            ): "events",
            pool.submit(_safe_fetch, f"/api/usage?user={quote(str(user_id))}", cookie=cookie): "usage",
        }
        results: dict[str, Any] = {}
        for fut in as_completed(futures):
            results[futures[fut]] = fut.result()

    raw = data.get("raw") or {}
    composed = _compose_usage_data(
        auth={"source": data.get("authSource"), "cookie": cookie},
        me={
            "id": user_id,
            "email": (data.get("user") or {}).get("email"),
            "name": (data.get("user") or {}).get("name"),
            "membershipType": (data.get("user") or {}).get("membership"),
        },
        summary=raw.get("summary"),
        period=raw.get("period"),
        usage=results.get("usage"),
        now=now,
        agg_today=results.get("today"),
        agg_week=results.get("week"),
        agg_month=results.get("month"),
        agg_cycle=results.get("cycle"),
        agg_all=results.get("all"),
        events=results.get("events"),
        partial=False,
    )
    # 保留首屏已算好的额度（避免 usage 覆盖造成闪烁）
    composed["quota"] = data.get("quota") or composed["quota"]
    composed["limits"] = data.get("limits") or composed["limits"]
    composed["cycle"] = data.get("cycle") or composed["cycle"]
    return {k: v for k, v in composed.items() if not str(k).startswith("_")}


def fetch_all_usage_data(manual_token: str | None = None) -> dict[str, Any]:
    data = fetch_usage_fast(manual_token)
    return enrich_usage_details(data)


def load_usage(
    *,
    manual_token: str | None = None,
    use_demo_when_logged_out: bool = True,
) -> dict[str, Any]:
    try:
        data = fetch_all_usage_data(manual_token)
        return {"data": data, "error": None, "updatedAt": int(time.time() * 1000)}
    except ApiError as exc:
        if use_demo_when_logged_out and exc.code in ("NO_SESSION", "AUTH_EXPIRED"):
            return {
                "data": get_demo_data(),
                "error": {"code": exc.code, "message": str(exc)},
                "updatedAt": int(time.time() * 1000),
            }
        raise
