"""供前端调用的 Python API（pywebview js_api）。"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable

from .api import ApiError, fetch_heatmap_for_year, load_usage
from .storage import SettingsStore


class AppBridge:
    def __init__(self, store: SettingsStore) -> None:
        self.store = store
        self.usage_cache: dict[str, Any] | None = None
        self._lock = threading.Lock()
        self._on_navigate: Callable[[str], None] | None = None
        self._on_float_expand: Callable[[bool], None] | None = None
        self._on_float_move: Callable[[float, float], None] | None = None
        self._on_quit: Callable[[], None] | None = None
        self._on_hide_main: Callable[[], None] | None = None
        self._on_show_float: Callable[[bool], None] | None = None
        self._broadcast: Callable[[dict[str, Any]], None] | None = None

    def bind(
        self,
        *,
        on_navigate=None,
        on_float_expand=None,
        on_float_move=None,
        on_quit=None,
        on_hide_main=None,
        on_show_float=None,
        broadcast=None,
    ) -> None:
        self._on_navigate = on_navigate
        self._on_float_expand = on_float_expand
        self._on_float_move = on_float_move
        self._on_quit = on_quit
        self._on_hide_main = on_hide_main
        self._on_show_float = on_show_float
        self._broadcast = broadcast

    def refresh_usage(self, broadcast: bool = True) -> dict[str, Any]:
        settings = self.store.get()
        with self._lock:
            try:
                self.usage_cache = load_usage(
                    manual_token=settings.get("manualToken") or None,
                    use_demo_when_logged_out=bool(settings.get("useDemoWhenLoggedOut", True)),
                )
            except ApiError as exc:
                self.usage_cache = {
                    "data": (self.usage_cache or {}).get("data"),
                    "error": {"code": exc.code, "message": str(exc)},
                    "updatedAt": int(time.time() * 1000),
                }
            except Exception as exc:
                self.usage_cache = {
                    "data": (self.usage_cache or {}).get("data"),
                    "error": {"code": "ERROR", "message": str(exc)},
                    "updatedAt": int(time.time() * 1000),
                }
            payload = self.usage_cache
        if broadcast and self._broadcast and payload:
            self._broadcast(payload)
        return payload or {"data": None, "error": {"message": "暂无数据"}, "updatedAt": int(time.time() * 1000)}

    # —— JS API ——
    def get_usage(self, force: bool = False) -> dict[str, Any]:
        if force or not self.usage_cache:
            return self.refresh_usage(broadcast=False)
        return self.usage_cache

    def refresh_usage_api(self) -> dict[str, Any]:
        return self.refresh_usage(broadcast=True)

    def get_heatmap(self, year: int) -> dict[str, Any]:
        settings = self.store.get()
        try:
            heatmap = fetch_heatmap_for_year(
                int(year),
                manual_token=settings.get("manualToken") or None,
                force=False,
            )
            return {"ok": True, "heatmap": heatmap}
        except Exception as exc:
            return {"ok": False, "error": {"message": str(exc)}, "heatmap": None}

    def get_settings(self) -> dict[str, Any]:
        return self.store.get()

    def set_settings(self, partial: dict[str, Any] | None = None) -> dict[str, Any]:
        settings = self.store.save(partial or {})
        if partial and "showFloat" in partial and self._on_show_float:
            self._on_show_float(bool(partial.get("showFloat")))
        return settings

    def open_dashboard(self) -> bool:
        if self._on_navigate:
            self._on_navigate("panels")
        return True

    def open_dashboard_detail(self) -> bool:
        if self._on_navigate:
            self._on_navigate("dashboard")
        return True

    def open_panels(self) -> bool:
        if self._on_navigate:
            self._on_navigate("panels")
        return True

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

    def quit_app(self) -> bool:
        if self._on_quit:
            self._on_quit()
        return True
