"""供前端调用的 Python API（pywebview js_api）。"""

from __future__ import annotations

import copy
import threading
import time
from datetime import datetime
from typing import Any, Callable

from .api import ApiError, enrich_usage_details, fetch_heatmap_for_year, fetch_usage_fast
from .auth import resolve_session_token
from .codex_usage import CodexUsage
from .codex_activity import CodexActivity
from .cursor_questions import add_cursor_questions
from .demo import get_demo_data
from .storage import SettingsStore, load_usage_cache, save_usage_cache
from .token_accounting import project_usage, project_heatmap, token_total


def _safe_settings_saved(cb: Callable[[dict[str, Any]], None], settings: dict[str, Any]) -> None:
    try:
        cb(settings)
    except Exception:
        pass


class AppBridge:
    def __init__(self, store: SettingsStore) -> None:
        self.store = store
        self.codex_usage = CodexUsage()
        self.codex_activity = CodexActivity()
        self.usage_cache: dict[str, Any] | None = load_usage_cache()
        self._lock = threading.Lock()
        self._heatmap_lock = threading.Lock()
        self._refresh_lock = threading.Lock()
        self._heatmap_running = False
        self._bg_refresh_running = False
        self._on_navigate: Callable[[str], None] | None = None
        self._on_float_expand: Callable[[bool], None] | None = None
        self._on_float_move: Callable[[float, float], None] | None = None
        self._on_quit: Callable[[], None] | None = None
        self._on_hide_main: Callable[[], None] | None = None
        self._on_show_float: Callable[[bool], None] | None = None
        self._on_login: Callable[[], dict[str, Any]] | None = None
        self._login_status: Callable[[], dict[str, Any]] | None = None
        self._broadcast: Callable[[dict[str, Any]], None] | None = None
        self._on_heatmap: Callable[[dict[str, Any]], None] | None = None
        self._on_settings_saved: Callable[[dict[str, Any]], None] | None = None
        self._heatmap_push: dict[str, Any] | None = None
        self.float_native: Any = None
        self.float_dock: Any = None

    def bind(
        self,
        *,
        on_navigate=None,
        on_float_expand=None,
        on_float_move=None,
        on_quit=None,
        on_hide_main=None,
        on_show_float=None,
        on_login=None,
        login_status=None,
        broadcast=None,
        on_heatmap=None,
        on_settings_saved=None,
    ) -> None:
        self._on_navigate = on_navigate
        self._on_float_expand = on_float_expand
        self._on_float_move = on_float_move
        self._on_quit = on_quit
        self._on_hide_main = on_hide_main
        self._on_show_float = on_show_float
        self._on_login = on_login
        self._login_status = login_status
        self._broadcast = broadcast
        self._on_heatmap = on_heatmap
        self._on_settings_saved = on_settings_saved

    def _public_payload(self, payload: dict[str, Any] | None) -> dict[str, Any]:
        if not payload:
            return {"data": None, "error": {"message": "暂无数据"}, "updatedAt": int(time.time() * 1000)}
        data = payload.get("data")
        if isinstance(data, dict):
            # raw/heatmap 很大，回传 pywebview 易失败；内部字段也不下发
            clean = {
                k: v
                for k, v in data.items()
                if not str(k).startswith("_") and k not in ("raw", "heatmap")
            }
            clean = project_usage(clean, bool(self.store.get().get("includeCachedTokens", False)))
            # 事件列表过长也会撑爆 JS 桥，截断即可满足详情页
            events = clean.get("events")
            if isinstance(events, list) and len(events) > 80:
                clean = {**clean, "events": events[:80]}
            return {**payload, "data": clean}
        return payload

    @staticmethod
    def _tokens_from_periods(periods: Any, include_cache: bool = False) -> dict[str, int | None]:
        if not isinstance(periods, dict):
            return {"today": None, "cycle": None}

        def total(key: str) -> int | None:
            p = periods.get(key)
            if not isinstance(p, dict):
                return None
            n = token_total(p, include_cache)
            has_signal = n > 0 or int(p.get("cache") or 0) > 0 or float(p.get("cost") or 0) > 0 or p.get("calls") is not None
            return n if has_signal else None

        return {"today": total("today"), "cycle": total("cycle")}

    def _ensure_card_tokens(
        self, card: dict[str, Any], full_payload: dict[str, Any] | None
    ) -> dict[str, Any]:
        """卡片 JSON 不含 periods 时，从完整缓存补 today/cycle token。"""
        data = card.get("data")
        if not isinstance(data, dict):
            return card
        usage = data.get("usageTokens")
        if isinstance(usage, dict) and usage.get("today") is not None:
            return card
        full_data = (full_payload or {}).get("data") if isinstance(full_payload, dict) else None
        if not isinstance(full_data, dict):
            return card
        tok = self._tokens_from_periods(full_data.get("periods"), bool(self.store.get().get("includeCachedTokens", False)))
        if tok["today"] is None and tok["cycle"] is None:
            return card
        data = {
            **data,
            "usageTokens": {
                "today": tok["today"] if tok["today"] is not None else 0,
                "cycle": tok["cycle"] if tok["cycle"] is not None else 0,
            },
        }
        return {**card, "data": data}

    def _card_payload(self, payload: dict[str, Any] | None) -> dict[str, Any]:
        """外层面板 / 广播专用：极小 JSON，避免 pywebview 回传失败。"""
        base = self._public_payload(payload)
        data = base.get("data")
        if not isinstance(data, dict):
            return {**base, "kind": "card"}
        user = data.get("user") if isinstance(data.get("user"), dict) else {}
        quota = data.get("quota") if isinstance(data.get("quota"), dict) else {}
        limits = data.get("limits") if isinstance(data.get("limits"), dict) else {}
        cycle = data.get("cycle") if isinstance(data.get("cycle"), dict) else {}
        periods = data.get("periods") if isinstance(data.get("periods"), dict) else {}

        is_partial = bool(data.get("partial"))

        def _period_token_total(key: str) -> int | None:
            p = periods.get(key)
            if not isinstance(p, dict):
                return None
            total = token_total(p, data.get("includeCachedTokens", False))
            has_signal = (
                total > 0
                or int(p.get("cache") or 0) > 0
                or float(p.get("cost") or 0) > 0
                or p.get("calls") is not None
            )
            # partial 首屏的空占位不能当成「今日 0」
            if is_partial and not has_signal:
                return None
            if not is_partial:
                return total
            return total if has_signal else None

        today_tokens = _period_token_total("today")
        cycle_tokens = _period_token_total("cycle")

        def _today_pool_tokens() -> dict[str, dict[str, int]] | None:
            models = data.get("models")
            if not isinstance(models, dict):
                return None
            today_models = models.get("today")
            if not isinstance(today_models, list) or not today_models:
                return None
            acc: dict[str, dict[str, int]] = {
                "cursor": {"tokens": 0, "input": 0, "output": 0},
                "other": {"tokens": 0, "input": 0, "output": 0},
            }
            seen = False
            for item in today_models:
                if not isinstance(item, dict):
                    continue
                pool = "cursor" if item.get("pool") == "cursor" else "other"
                inp = int(item.get("input") or 0)
                out = int(item.get("output") or 0)
                tok_raw = item.get("tokens")
                tok = int(tok_raw) if tok_raw is not None else inp + out
                acc[pool]["input"] += inp
                acc[pool]["output"] += out
                acc[pool]["tokens"] += tok
                seen = True
            if not seen:
                return None
            return acc

        today_pool = _today_pool_tokens()
        if today_tokens is None and today_pool:
            pooled = sum(int(v.get("tokens") or 0) for v in today_pool.values())
            if pooled > 0 or not is_partial:
                today_tokens = pooled

        slim = {
            "includeCachedTokens": data.get("includeCachedTokens", False),
            "tokenBasis": data.get("tokenBasis"),
            "demo": bool(data.get("demo")),
            "partial": is_partial,
            "fetchedAt": data.get("fetchedAt"),
            "authSource": data.get("authSource"),
            "user": {
                "email": user.get("email"),
                "membership": user.get("membership") or user.get("plan") or user.get("subscriptionStatus"),
            },
            "cycle": {
                "start": cycle.get("start"),
                "end": cycle.get("end"),
                "resetAt": cycle.get("resetAt") or cycle.get("end"),
                "label": cycle.get("label"),
            },
            "quota": {
                "total": quota.get("total"),
                "used": quota.get("used"),
                "remaining": quota.get("remaining"),
                "usedPercent": quota.get("usedPercent"),
                "remainingPercent": quota.get("remainingPercent"),
                "autoPercent": quota.get("autoPercent"),
                "apiPercent": quota.get("apiPercent"),
                "cursorModelsPercent": quota.get("cursorModelsPercent"),
                "otherModelsPercent": quota.get("otherModelsPercent"),
            },
            "limits": {
                "cursorModelsPercent": limits.get("cursorModelsPercent"),
                "otherModelsPercent": limits.get("otherModelsPercent"),
            },
        }
        if today_tokens is not None or cycle_tokens is not None:
            slim["usageTokens"] = {
                "today": today_tokens if today_tokens is not None else 0,
                "cycle": cycle_tokens if cycle_tokens is not None else 0,
            }
        if today_pool:
            slim["todayPoolTokens"] = today_pool
        return {
            "kind": "card",
            "data": slim,
            "error": base.get("error"),
            "updatedAt": base.get("updatedAt") or int(time.time() * 1000),
        }

    def _detail_payload(self, payload: dict[str, Any] | None) -> dict[str, Any]:
        """详情页用：含 models / events / periods，不含 heatmap。"""
        public = self._public_payload(payload)
        data = public.get("data")
        if isinstance(data, dict) and not data.get("demo") and data.get("events"):
            public = {**public, "data": {**data, "events": add_cursor_questions(data["events"])}}
        return {**public, "kind": "detail"}

    def _set_cache(self, payload: dict[str, Any]) -> dict[str, Any]:
        public = self._public_payload(payload)
        with self._lock:
            self.usage_cache = payload
        save_usage_cache(public)
        return public

    def _emit(self, payload: dict[str, Any]) -> None:
        """延迟推送精简数据，避免与 JS API 回调打架 / 大 JSON 撑爆 evaluate_js。"""
        if not self._broadcast:
            return
        def run() -> None:
            time.sleep(0.08)
            try:
                self._broadcast(payload)
            except Exception:
                pass

        threading.Thread(target=run, daemon=True).start()

    def _cached_payload(self) -> dict[str, Any] | None:
        with self._lock:
            cached = self.usage_cache
        if not cached or not isinstance((cached or {}).get("data"), dict):
            disk = load_usage_cache()
            if disk and isinstance(disk.get("data"), dict):
                with self._lock:
                    if not self.usage_cache or not isinstance((self.usage_cache or {}).get("data"), dict):
                        self.usage_cache = disk
                    cached = self.usage_cache
        return cached

    def _schedule_heatmap(self, force: bool = False) -> None:
        with self._heatmap_lock:
            if self._heatmap_running:
                return
            self._heatmap_running = True

        def job() -> None:
            try:
                settings = self.store.get()
                year = datetime.now().year
                heatmap = fetch_heatmap_for_year(
                    year,
                    manual_token=settings.get("manualToken") or None,
                    force=force,
                )
                with self._lock:
                    if not self.usage_cache or not isinstance(self.usage_cache.get("data"), dict):
                        return
                    if self.usage_cache["data"].get("demo"):
                        return
                    data = copy.copy(self.usage_cache["data"])
                    data["heatmap"] = heatmap
                    self.usage_cache = {
                        **self.usage_cache,
                        "data": data,
                        "updatedAt": int(time.time() * 1000),
                    }
                    payload = self.usage_cache
                save_usage_cache(self._public_payload(payload))
                self._emit(payload)
            except Exception:
                pass
            finally:
                with self._heatmap_lock:
                    self._heatmap_running = False

        threading.Thread(target=job, daemon=True).start()

    @staticmethod
    def _models_empty(models: Any) -> bool:
        if not isinstance(models, dict) or not models:
            return True
        return not any(isinstance(v, list) and v for v in models.values())

    @staticmethod
    def _periods_empty(periods: Any) -> bool:
        if not isinstance(periods, dict) or not periods:
            return True
        for p in periods.values():
            if isinstance(p, dict) and (
                float(p.get("cost") or 0) > 0
                or int(p.get("input") or 0) > 0
                or int(p.get("output") or 0) > 0
            ):
                return False
        return True

    def _merge_preserve_details(self, new_data: dict[str, Any], old_data: dict | None) -> dict[str, Any]:
        """刷新中途（partial）不丢弃旧的模型/记录，避免页面被清空。"""
        if not isinstance(old_data, dict) or old_data.get("demo"):
            return new_data
        if new_data.get("demo"):
            return new_data
        merged = copy.copy(new_data)
        if self._models_empty(merged.get("models")) and not self._models_empty(old_data.get("models")):
            merged["models"] = old_data["models"]
        if not (merged.get("events") or []) and (old_data.get("events") or []):
            merged["events"] = old_data["events"]
        if self._periods_empty(merged.get("periods")) and not self._periods_empty(old_data.get("periods")):
            merged["periods"] = old_data["periods"]
        if not merged.get("heatmap") and old_data.get("heatmap"):
            merged["heatmap"] = old_data["heatmap"]
        return merged

    def _cached_real_data(self) -> dict[str, Any] | None:
        with self._lock:
            old = (self.usage_cache or {}).get("data")
        if isinstance(old, dict) and not old.get("demo"):
            return old
        return None

    def refresh_usage(self, broadcast: bool = True) -> dict[str, Any]:
        """两阶段刷新。禁止在 JS 调用栈里同步等待本方法。"""
        settings = self.store.get()
        manual = settings.get("manualToken") or None
        use_demo = bool(settings.get("useDemoWhenLoggedOut", True))
        prev = self._cached_real_data()

        with self._refresh_lock:
            try:
                fast_data = fetch_usage_fast(manual)
                fast_data = self._merge_preserve_details(fast_data, prev)
                phase1 = {
                    "data": fast_data,
                    "error": None,
                    "updatedAt": int(time.time() * 1000),
                }
            except ApiError as exc:
                # 未登录：保留旧真实数据；无旧数据时才考虑演示数据
                if exc.code in ("NO_SESSION", "AUTH_EXPIRED"):
                    if prev:
                        phase1 = {
                            "data": prev,
                            "error": {"code": exc.code, "message": str(exc)},
                            "updatedAt": int(time.time() * 1000),
                        }
                    elif use_demo:
                        phase1 = {
                            "data": get_demo_data(),
                            "error": {"code": exc.code, "message": str(exc)},
                            "updatedAt": int(time.time() * 1000),
                        }
                    else:
                        phase1 = {
                            "data": None,
                            "error": {"code": exc.code, "message": str(exc)},
                            "updatedAt": int(time.time() * 1000),
                        }
                else:
                    phase1 = {
                        "data": prev,
                        "error": {"code": exc.code, "message": str(exc)},
                        "updatedAt": int(time.time() * 1000),
                    }
            except Exception as exc:
                phase1 = {
                    "data": prev,
                    "error": {"code": "ERROR", "message": str(exc)},
                    "updatedAt": int(time.time() * 1000),
                }

            # 无有效数据时不要用 None 覆盖已有缓存
            if phase1.get("data") is None and prev:
                phase1["data"] = prev

            if phase1.get("data") is not None:
                public1 = self._set_cache(phase1)
            else:
                public1 = phase1
            if broadcast:
                self._emit(public1)

            data = phase1.get("data")
            err_code = (phase1.get("error") or {}).get("code")
            # 未登录 / 演示数据：到此为止
            if err_code in ("NO_SESSION", "AUTH_EXPIRED") or not isinstance(data, dict) or data.get("demo"):
                return public1

            try:
                enriched = enrich_usage_details(data)
                enriched = self._merge_preserve_details(enriched, prev)
                phase2 = {
                    "data": enriched,
                    "error": None,
                    "updatedAt": int(time.time() * 1000),
                }
                public2 = self._set_cache(phase2)
                if broadcast:
                    self._emit(phase2)
                self._schedule_heatmap(force=False)
                return public2
            except Exception as exc:
                err_payload = {
                    **public1,
                    "error": {"code": "DETAILS_ERROR", "message": str(exc)},
                    "updatedAt": int(time.time() * 1000),
                }
                if broadcast:
                    self._emit(err_payload)
                return err_payload

    def refresh_usage_background(self) -> bool:
        with self._lock:
            if self._bg_refresh_running:
                return False
            self._bg_refresh_running = True

        def job() -> None:
            try:
                self.refresh_usage(broadcast=True)
            finally:
                with self._lock:
                    self._bg_refresh_running = False

        threading.Thread(target=job, daemon=True).start()
        return True

    # —— JS API：全部快速返回，网络刷新走后台推送 ——
    def get_usage(self, force: bool = False) -> dict[str, Any]:
        cached = self._cached_payload()
        # 永远先返回缓存；force 也只触发后台刷新，避免卡死 WebView 回调
        self.refresh_usage_background()
        return self._public_payload(cached)

    def get_usage_summary(self) -> dict[str, Any]:
        """外层面板专用：只回额度摘要，保证 pywebview 能稳定拿到。"""
        cached = self._cached_payload()
        self.refresh_usage_background()
        card = self._card_payload(cached)
        return self._ensure_card_tokens(card, cached)

    def get_usage_tokens(self) -> dict[str, Any]:
        """悬浮窗专用：极小 payload，只回今日/本周期 token（读完整缓存 periods）。"""
        cached = self._cached_payload()
        data = (cached or {}).get("data") if isinstance(cached, dict) else None
        if not isinstance(data, dict):
            return {"ok": False, "today": None, "cycle": None, "partial": True}
        include_cache = bool(self.store.get().get("includeCachedTokens", False))
        tok = self._tokens_from_periods(data.get("periods"), include_cache)
        return {
            "ok": True,
            "includeCachedTokens": include_cache,
            "today": tok["today"],
            "cycle": tok["cycle"],
            "partial": bool(data.get("partial")),
            "updatedAt": (cached or {}).get("updatedAt") or int(time.time() * 1000),
        }

    def get_cursor_activity(self) -> dict[str, Any]:
        """悬浮窗：Cursor 是否在前台/高 CPU（近似工作中）。"""
        from .cursor_activity import probe_cursor_activity

        return probe_cursor_activity()

    def get_codex_activity(self) -> dict[str, Any]:
        return self.codex_activity.probe()

    def refresh_usage_api(self) -> dict[str, Any]:
        """只触发后台刷新；真正数据靠推送 / get_usage / HTML bootstrap。"""
        self.refresh_usage_background()
        return {"ok": True, "kind": "ack"}

    def request_refresh(self) -> dict[str, Any]:
        """与 refresh_usage_api 相同；供 pywebview 暴露时的备用方法名。"""
        return self.refresh_usage_api()

    def get_usage_detail(self) -> dict[str, Any]:
        """详情页主动拉取（仍可能被 pywebview 丢包；优先配合 bootstrap/推送）。"""
        cached = self._cached_payload()
        self.refresh_usage_background()
        return self._detail_payload(cached)

    def get_heatmap(self, year: int) -> dict[str, Any]:
        """热力数据很大：API 立刻返回，后台算完后走 __seeUtokenHeatmapPush。"""
        y = int(year)

        def job() -> None:
            settings = self.store.get()
            try:
                heatmap = fetch_heatmap_for_year(
                    y,
                    manual_token=settings.get("manualToken") or None,
                    force=False,
                )
                with self._lock:
                    if self.usage_cache and isinstance(self.usage_cache.get("data"), dict):
                        if y == datetime.now().year:
                            data = copy.copy(self.usage_cache["data"])
                            data["heatmap"] = heatmap
                            self.usage_cache = {**self.usage_cache, "data": data}
                self._heatmap_push = {"ok": True, "heatmap": self._display_heatmap(heatmap), "year": y}
                if self._on_heatmap:
                    try:
                        self._on_heatmap(self._heatmap_push)
                    except Exception:
                        pass
            except Exception as exc:
                self._heatmap_push = {"ok": False, "error": {"message": str(exc)}, "year": y}

        threading.Thread(target=job, daemon=True).start()
        return {"ok": True, "year": y, "deferred": True}

    def get_heatmap_result(self) -> dict[str, Any]:
        """取最近一次热力结果（仍可能很大；优先用推送）。"""
        result = getattr(self, "_heatmap_push", None) or {"ok": False, "heatmap": None}
        if isinstance(result.get("heatmap"), dict):
            return {**result, "heatmap": self._display_heatmap(result["heatmap"])}
        return result

    def get_settings(self) -> dict[str, Any]:
        return self.store.get()

    def _display_heatmap(self, heatmap: dict) -> dict:
        return project_heatmap(heatmap, bool(self.store.get().get("includeCachedTokens", False)))

    def set_settings(self, partial: dict[str, Any] | None = None) -> dict[str, Any]:
        settings = self.store.save(partial or {})
        if partial and "includeCachedTokens" in partial:
            self._emit(self._cached_payload())
            def push_heatmap():
                cached_heatmap = ((self._cached_payload() or {}).get("data") or {}).get("heatmap")
                if isinstance(cached_heatmap, dict):
                    try:
                        self._heatmap_push = {"ok": True, "heatmap": self._display_heatmap(cached_heatmap), "year": cached_heatmap['year']}
                        if self._on_heatmap:
                            self._on_heatmap(self._heatmap_push)
                    except Exception:
                        pass
            threading.Thread(target=push_heatmap, daemon=True).start()
        if partial and "showFloat" in partial and self._on_show_float:
            self._on_show_float(bool(partial.get("showFloat")))
        # 玻璃同步会碰 AppKit；不能堵在 JS API 回调里，否则 WebView 点不了完成/取消
        if self._on_settings_saved:
            cb = self._on_settings_saved
            threading.Thread(target=lambda: _safe_settings_saved(cb, settings), daemon=True).start()
        return settings

    def set_float_glass_shape(self, payload: dict | None = None) -> bool:
        """前端上报悬浮窗轮廓（rail + pop + 尾巴），驱动 macOS 异形 Liquid Glass。"""
        if self.float_dock:
            self.float_dock.update_geometry(payload)
        if self.float_native:
            try:
                self.float_native.update_shape(payload)
            except Exception:
                pass
        return True

    def set_float_dragging(self, dragging: bool = False) -> bool:
        if self.float_dock:
            self.float_dock.set_dragging(bool(dragging))
        return True

    def reveal_float_dock(self) -> bool:
        if self.float_dock:
            self.float_dock.reveal()
        return True

    def get_native_material_state(self) -> dict[str, Any]:
        if self.float_native:
            return self.float_native.get_state()
        return {
            "type": "transparent",
            "reducedTransparency": False,
            "highContrast": False,
            "fallbackReason": None,
            "liquidGlassSupported": False,
        }

    def _defer_navigate(self, page: str) -> bool:
        """先返回 JS 回调，再跳转，避免 load_url 清掉 _returnValuesCallbacks。"""
        on_nav = self._on_navigate
        if not on_nav:
            return False

        def run() -> None:
            time.sleep(0.12)
            try:
                on_nav(page)
            except Exception:
                pass

        threading.Thread(target=run, daemon=True).start()
        return True

    def open_dashboard(self) -> bool:
        return self._defer_navigate("panels")

    def get_codex_usage(self, summary: bool = False, year: int | None = None, refresh: bool = False) -> dict[str, Any]:
        payload = self.codex_usage.get(
            summary=summary, year=year, refresh=refresh,
            auto_refresh_minutes=self.store.get().get("codexAutoRefreshMinutes", 1),
        )
        return {**payload, "data": project_usage(payload["data"], bool(self.store.get().get("includeCachedTokens", False)))}

    def open_dashboard_detail(self, provider: str = "cursor") -> bool:
        return self._defer_navigate("codex" if provider == "codex" else "dashboard")

    def open_panels(self) -> bool:
        return self._defer_navigate("panels")

    def hide_dashboard(self) -> bool:
        if self._on_hide_main:
            self._on_hide_main()
        return True

    def set_float_expanded(self, expanded: bool) -> bool:
        self.store.save({"floatCollapsed": not bool(expanded)})
        if self._on_float_expand:
            self._on_float_expand(bool(expanded))
        return True

    def move_float_by(self, dx: float, dy: float) -> bool:
        if self._on_float_move:
            self._on_float_move(float(dx or 0), float(dy or 0))
        return True

    def perform_haptic(self, kind: str = "hover") -> bool:
        from .haptic import perform_haptic

        return perform_haptic(kind)

    def quit_app(self) -> bool:
        if self._on_quit:
            self._on_quit()
        return True

    def start_login(self) -> dict[str, Any]:
        if not self._on_login:
            return {"ok": False, "error": "登录功能不可用"}
        try:
            return self._on_login() or {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def get_login_status(self) -> dict[str, Any]:
        if self._login_status:
            try:
                return self._login_status()
            except Exception as exc:
                return {"open": False, "done": False, "error": str(exc)}
        return {"open": False, "done": False}

    def get_auth_hint(self) -> dict[str, Any]:
        settings = self.store.get()
        auth = resolve_session_token(settings.get("manualToken") or None)
        return {
            "hasSession": bool(auth.get("cookie")),
            "source": auth.get("source") or "none",
        }
