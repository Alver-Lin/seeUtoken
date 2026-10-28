"""seeUtoken 桌面应用：主窗口 + 系统托盘。"""

from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import webview

from .bridge import AppBridge
from .float_native_material import FloatNativeMaterialController, _run_on_main, _ns_window_for
from .main_native_material import MainNativeMaterialController
from .float_pointer import FloatPointerController
from .float_dock import FloatDockController
from .storage import DEFAULT_PANELS, SettingsStore, normalize_float_glass_style
from .resources import prepare_ui, resource_root

ROOT = resource_root()
UI, _UI_TEMPORARY = prepare_ui(ROOT)
ASSETS = ROOT / "assets"

FLOAT_COLLAPSED = (72, 72)
FLOAT_EXPANDED_WIDTH = 400
_BOOTSTRAP_RE = re.compile(
    r"\s*<script id=\"seeutoken-bootstrap\">[\s\S]*?</script>",
    re.MULTILINE,
)
_DASH_BOOTSTRAP_RE = re.compile(
    r"\s*<script id=\"seeutoken-dash-bootstrap\">[\s\S]*?</script>",
    re.MULTILINE,
)
_FLOAT_BOOTSTRAP_RE = re.compile(
    r"\s*<script id=\"seeutoken-float-bootstrap\">[\s\S]*?</script>",
    re.MULTILINE,
)


def _file_uri(path: Path) -> str:
    return path.resolve().as_uri()


def _atomic_write_text(path: Path, text: str) -> None:
    """原子写入：先写同目录临时文件再 replace，避免 WKWebView 读到写了一半的 HTML。"""
    tmp = path.with_name(f"{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


class FloatBridge:
    """悬浮球专用 API：不提供 get_usage/get_heatmap，避免与主窗口回调串台。"""

    def __init__(self, main: AppBridge) -> None:
        self._main = main

    def get_settings(self):
        return self._main.get_settings()

    def set_settings(self, partial=None):
        return self._main.set_settings(partial)

    def get_native_material_state(self):
        return self._main.get_native_material_state()

    def set_float_glass_shape(self, payload=None):
        return self._main.set_float_glass_shape(payload)

    def set_float_expanded(self, expanded: bool = False):
        return self._main.set_float_expanded(expanded)

    def move_float_by(self, dx: float = 0, dy: float = 0):
        return self._main.move_float_by(dx, dy)

    def set_float_dragging(self, dragging=False):
        return self._main.set_float_dragging(dragging)

    def reveal_float_dock(self):
        return self._main.reveal_float_dock()

    def open_dashboard(self):
        return self._main.open_dashboard()

    def open_dashboard_detail(self, provider="cursor"):
        return self._main.open_dashboard_detail(provider)

    def get_codex_usage(self, summary=False, year=None, refresh=False):
        return self._main.get_codex_usage(summary, year, refresh)

    def open_panels(self):
        return self._main.open_panels()

    def hide_dashboard(self):
        return self._main.hide_dashboard()

    def quit_app(self):
        return self._main.quit_app()

    def get_usage_summary(self):
        return self._main.get_usage_summary()

    def get_usage_tokens(self):
        return self._main.get_usage_tokens()

    def refresh_usage_api(self):
        return self._main.refresh_usage_api()

    def get_cursor_activity(self):
        return self._main.get_cursor_activity()

    def get_codex_activity(self):
        return self._main.get_codex_activity()

    def perform_haptic(self, kind: str = "hover"):
        return self._main.perform_haptic(kind)

LOGIN_URL = "https://www.cursor.com/login"
SESSION_COOKIE = "WorkosCursorSessionToken"


def _extract_session_token(cookies) -> str | None:
    """从 pywebview get_cookies() 结果里取出 WorkosCursorSessionToken。"""
    if not cookies:
        return None
    for item in cookies:
        try:
            # SimpleCookie 或 dict-like
            if hasattr(item, "items"):
                for name, morsel in item.items():
                    if name == SESSION_COOKIE:
                        value = getattr(morsel, "value", None) or str(morsel)
                        if value and len(str(value)) > 20:
                            return str(value)
            if isinstance(item, dict):
                if item.get("name") == SESSION_COOKIE and item.get("value"):
                    return str(item["value"])
        except Exception:
            continue
    return None


class SeeUtokenApp:
    def __init__(self) -> None:
        self.store = SettingsStore()
        self.bridge = AppBridge(self.store)
        self.float_native = FloatNativeMaterialController(on_ready=self._show_prepared_float)
        self.main_native = MainNativeMaterialController()
        self.float_pointer = FloatPointerController()
        self.float_dock = FloatDockController(
            persist=lambda x, y: self.store.save({"floatX": x, "floatY": y, "floatCollapsed": False}),
            settings=self.store.get(),
        )
        self.bridge.float_dock = self.float_dock
        self.bridge.float_native = self.float_native
        self.float_bridge = FloatBridge(self.bridge)
        self.main_win: webview.Window | None = None
        self.float_win: webview.Window | None = None
        self.login_win: webview.Window | None = None
        self._tray = None
        self._app_delegate = None
        self._refresh_stop = threading.Event()
        self._login_poll_stop = threading.Event()
        self._quitting = False
        self._login_lock = threading.Lock()
        self._login_done = False
        self._float_loaded = False
        self._float_ready = False
        self._main_loaded = False
        self._ui_port = 0
        self._ui_server: ThreadingHTTPServer | None = None

    def _sync_float_native_material(self, settings: dict | None = None) -> None:
        if not self.float_win:
            return
        s = settings if settings is not None else self.store.get()
        appearance = json.dumps(self._float_settings_payload(s), ensure_ascii=False)
        try:
            self.float_win.evaluate_js(
                f"window.__seeUtokenFloatSettings={appearance};"
                "window.__seeUtokenApplyFloatSettings?.(window.__seeUtokenFloatSettings);"
            )
        except Exception:
            pass  # The bootstrap and periodic settings read also reconcile the list.
        self.float_dock.sync(s)
        if sys.platform != "darwin":
            self.float_win.on_top = bool(s.get("floatAlwaysOnTop", True))

        def push(win, js: str) -> None:
            try:
                win.evaluate_js(js)
            except Exception:
                pass

        # sync queues AppKit work; only publish after that work has completed.
        self.float_native.sync(s, on_complete=lambda: self.float_native.push_to_webview(push))
        self._set_float_visible(bool(s.get("showFloat", True)))

    def _sync_main_appearance(self, settings: dict | None = None) -> None:
        if not self.main_win:
            return
        s = settings if settings is not None else self.store.get()
        payload = json.dumps(self._float_settings_payload(s), ensure_ascii=False)
        try:
            self.main_win.evaluate_js(
                f"window.__seeUtokenFloatSettings={payload};"
                "window.__seeUtokenApplyFloatSettings?.(window.__seeUtokenFloatSettings);"
            )
        except Exception:
            pass
        self.main_native.sync(s, on_complete=lambda: self.main_native.push_to_webview(
            lambda win, js: win.evaluate_js(js)))

    def _sync_appearance(self, settings: dict | None = None) -> None:
        self._sync_main_appearance(settings)
        self._sync_float_native_material(settings)

    def _main_appearance_bootstrap(self) -> str:
        mode = self._float_settings_payload(self.store.get())["floatGlassStyle"]
        settings = json.dumps({"floatGlassStyle": mode}, ensure_ascii=False)
        native = json.dumps(self.main_native.get_state(), ensure_ascii=False)
        return (
            f"window.__seeUtokenFloatSettings={settings};"
            f"window.__seeUtokenNativeMaterial={native};"
            f"document.documentElement.dataset.sutAppearance={json.dumps(mode)};"
            f"document.documentElement.style.colorScheme={'light' if mode == 'light' else 'dark'!r};"
            f"document.documentElement.style.backgroundColor={'#f5f7f9' if mode == 'light' else '#111824'!r};"
        )

    def _show_prepared_float(self) -> None:
        """Reveal only after geometry, native material and WebView classes agree."""
        def ready() -> None:
            self._float_ready = True
            self._set_float_visible(bool(self.store.get().get("showFloat", True)))
            print("[seeUtoken] float appearance ready", flush=True)

        self.float_native.push_to_webview(
            lambda win, js: win.evaluate_js(js),
            on_applied=ready,
        )

    def _inject_script_before_module(self, html_path: Path, script_id: str, body_js: str, strip_re) -> None:
        if not html_path.exists():
            return
        boot = f'<script id="{script_id}">{body_js}</script>'
        html = html_path.read_text(encoding="utf-8")
        html = strip_re.sub("", html)
        mod = re.search(r'<script\s+type="module"', html)
        if mod:
            html = html[: mod.start()] + boot + "\n    " + html[mod.start() :]
        else:
            html = html.replace("</head>", f"    {boot}\n  </head>", 1)
        _atomic_write_text(html_path, html)

    def _inject_panels_bootstrap(self) -> None:
        """把额度摘要内联进 panels HTML，Vue 启动前就能读到，彻底绕过 API 回传。"""
        try:
            card = self.bridge._card_payload(self.bridge._cached_payload())
            raw = json.dumps(card, ensure_ascii=False, separators=(",", ":"))
            js = self._main_appearance_bootstrap() + f"window.__seeUtokenLastCard=JSON.parse({json.dumps(raw)});"
            self._inject_script_before_module(
                UI / "panels" / "index.html",
                "seeutoken-bootstrap",
                js,
                _BOOTSTRAP_RE,
            )
        except Exception:
            pass

    def _inject_dashboard_bootstrap(self) -> None:
        """详情页：内联 models/events/periods + 热力图，避免空白模块。"""
        try:
            cached = self.bridge._cached_payload()
            detail = self.bridge._detail_payload(cached)
            detail_literal = json.dumps(json.dumps(detail, ensure_ascii=False, separators=(',', ':'))).replace('<', r'\u003c')
            parts = [
                self._main_appearance_bootstrap(),
                f"window.__seeUtokenLastDetail=JSON.parse({detail_literal});",
                "window.__seeUtokenLastCard=window.__seeUtokenLastCard||null;",
            ]
            data = (cached or {}).get("data") if isinstance(cached, dict) else None
            heatmap = data.get("heatmap") if isinstance(data, dict) else None
            if isinstance(heatmap, dict) and heatmap.get("months"):
                heat = {"ok": True, "heatmap": self.bridge._display_heatmap(heatmap), "year": heatmap.get("year")}
                parts.append(
                    f"window.__seeUtokenLastHeatmap=JSON.parse({json.dumps(json.dumps(heat, ensure_ascii=False, separators=(',', ':')))});"
                )
            self._inject_script_before_module(
                UI / "dashboard" / "index.html",
                "seeutoken-dash-bootstrap",
                "".join(parts),
                _DASH_BOOTSTRAP_RE,
            )
        except Exception:
            pass

    @staticmethod
    def _float_settings_payload(settings: dict) -> dict:
        return {
            "floatGlassStyle": normalize_float_glass_style(settings.get("floatGlassStyle")),
            "includeCachedTokens": bool(settings.get("includeCachedTokens", False)),
            "panels": [{"type": panel.get("type") or panel.get("provider") or "cursor"}
                       for panel in settings.get("panels", DEFAULT_PANELS) if isinstance(panel, dict)],
        }

    def _inject_float_bootstrap(self) -> None:
        """悬浮窗：内联额度卡片，避免 partial 推送把今日 Token 打成 0。"""
        try:
            cached = self.bridge._cached_payload()
            card = self.bridge._ensure_card_tokens(
                self.bridge._card_payload(cached),
                cached,
            )
            raw = json.dumps(card, ensure_ascii=False, separators=(",", ":"))
            native = json.dumps(
                self.float_native.get_state(),
                ensure_ascii=False,
                separators=(",", ":"),
            )
            settings = self.store.get()
            appearance = json.dumps(self._float_settings_payload(settings), ensure_ascii=False, separators=(",", ":"))
            js = (
                f"window.__seeUtokenLastCard=JSON.parse({json.dumps(raw)});"
                f"window.__seeUtokenNativeMaterial=JSON.parse({json.dumps(native)});"
                f"window.__seeUtokenFloatSettings=JSON.parse({json.dumps(appearance)});"
            )
            self._inject_script_before_module(
                UI / "float" / "index.html",
                "seeutoken-float-bootstrap",
                js,
                _FLOAT_BOOTSTRAP_RE,
            )
        except Exception:
            pass

    def _start_ui_server(self) -> int:
        """用本机 HTTP 提供 ui/，避开 macOS 26 WKWebView 对 file:// ES module 的白屏。"""
        if self._ui_port:
            return self._ui_port

        ui_root = str(UI)
        bridge = self.bridge

        class Handler(SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=ui_root, **kwargs)

            def do_GET(self):
                parsed = urlparse(self.path)
                if parsed.path not in ("/api/codex-usage", "/api/codex-activity"):
                    return super().do_GET()
                origin = f"http://127.0.0.1:{self.server.server_port}"
                if self.headers.get("Host") != origin.removeprefix("http://") or self.headers.get("Origin", origin) != origin:
                    self.send_error(403)
                    return
                query = parse_qs(parsed.query)
                try:
                    if parsed.path == "/api/codex-activity":
                        result = bridge.get_codex_activity()
                    else:
                        year = int(query["year"][0]) if "year" in query else None
                        result = bridge.get_codex_usage(query.get("summary") == ["1"], year, query.get("refresh") == ["1"])
                except (TypeError, ValueError):
                    self.send_error(400)
                    return
                body = json.dumps(result, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def end_headers(self):
                self.send_header("Cache-Control", "no-store")
                super().end_headers()

            def log_message(self, format, *args):  # noqa: A003
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._ui_server = server
        self._ui_port = int(server.server_address[1])
        threading.Thread(target=server.serve_forever, daemon=True).start()
        print(f"[seeUtoken] UI http://127.0.0.1:{self._ui_port}/", flush=True)
        return self._ui_port

    def _page(self, name: str) -> str:
        port = self._start_ui_server()
        if name == "panels":
            self._inject_panels_bootstrap()
        elif name == "dashboard":
            self._inject_dashboard_bootstrap()
        elif name == "float":
            self._inject_float_bootstrap()
        return f"http://127.0.0.1:{port}/{name}/index.html"

    def _eval_push(self, win, payload: dict, hook: str = "__seeUtokenPush") -> None:
        """单向推送：不走 pywebview API 回传，避免多窗口回调串台/丢包。"""
        if not win:
            return
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        if hook == "__seeUtokenPush":
            last_key = "__seeUtokenLastCard"
        elif hook == "__seeUtokenDetailPush":
            last_key = "__seeUtokenLastDetail"
        else:
            last_key = "__seeUtokenLastHeatmap"
        js = (
            f"window.{last_key}=JSON.parse({json.dumps(raw)});"
            f"window.{hook}&&window.{hook}(window.{last_key})"
        )
        try:
            win.evaluate_js(js)
        except Exception:
            pass

    def _push_card(self, payload: dict | None = None) -> None:
        cached = self.bridge._cached_payload() if payload is None else payload
        if payload is not None and isinstance(payload, dict):
            card = self.bridge._ensure_card_tokens(
                self.bridge._card_payload(payload),
                payload,
            )
        else:
            card = self.bridge._ensure_card_tokens(
                self.bridge._card_payload(cached),
                cached,
            )
        if not isinstance(card, dict):
            return
        for win in (self.main_win, self.float_win):
            self._eval_push(win, card, "__seeUtokenPush")

    def _push_detail(self, payload: dict | None = None) -> None:
        detail = payload if payload is not None else self.bridge._detail_payload(self.bridge._cached_payload())
        if not isinstance(detail, dict):
            return
        self._eval_push(self.main_win, detail, "__seeUtokenDetailPush")

    def _broadcast(self, payload: dict) -> None:
        # 外层/悬浮球：精简 card；主窗口额外推详情（模型/记录）
        self._push_card(payload)
        try:
            if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
                detail = self.bridge._detail_payload(payload)
            else:
                detail = self.bridge._detail_payload(self.bridge._cached_payload())
            self._eval_push(self.main_win, detail, "__seeUtokenDetailPush")
        except Exception:
            pass

    def _navigate(self, page: str) -> None:
        if self._quitting or not self.main_win:
            return
        url = self._page("dashboard" if page in ("dashboard", "codex") else "panels")
        if page == "codex":
            url += "?provider=codex"
        title = "seeUtoken · Codex 用量" if page == "codex" else (
            "seeUtoken · Cursor 用量" if page == "dashboard" else "seeUtoken · 模型额度")
        try:
            self.main_win.set_title(title)
            self.main_win.load_url(url)
        except Exception:
            pass
        self._show_main()
        # 进详情后再推一次明细 + 触发热力
        if page == "dashboard":
            def after():
                time.sleep(0.35)
                try:
                    self._push_detail()
                except Exception:
                    pass
                try:
                    # 热力放后台算，算完走 __seeUtokenHeatmapPush
                    year = datetime.now().year
                    threading.Thread(
                        target=lambda: self.bridge.get_heatmap(year),
                        daemon=True,
                    ).start()
                except Exception:
                    pass

            threading.Thread(target=after, daemon=True).start()

    def _hide_main(self) -> None:
        if self.main_win:
            try:
                self.main_win.hide()
            except Exception:
                pass

    def _show_main(self) -> None:
        if self._quitting or not self.main_win:
            return

        def show() -> None:
            if self._quitting:
                return
            if sys.platform == "darwin":
                ns = _ns_window_for(self.main_win)
                if ns is not None:
                    from AppKit import NSApplication

                    app = NSApplication.sharedApplication()
                    if ns.isMiniaturized():
                        ns.deminiaturize_(None)
                    app.unhide_(None)
                    app.activateIgnoringOtherApps_(True)
                    ns.makeKeyAndOrderFront_(None)
                    return
            try:
                self.main_win.restore()
                self.main_win.show()
            except Exception:
                pass

        if sys.platform == "darwin":
            _run_on_main(show)
        else:
            show()

    def _install_macos_lifecycle(self) -> None:
        if sys.platform != "darwin":
            return

        def install() -> None:
            if not self._quitting:
                from .mac_lifecycle import install_app_delegate

                self._app_delegate = install_app_delegate(self._show_main, self._quit)

        _run_on_main(install)

    def _set_float_visible(self, visible: bool) -> None:
        if self._quitting or not self.float_win:
            return
        visible = bool(visible and self._float_ready and self._float_panel_type_count() > 0)
        try:
            if visible:
                self.float_win.show()
            else:
                self.float_win.hide()
            self.float_dock.set_visible(visible)
        except Exception:
            pass

    def _float_panel_type_count(self, settings: dict | None = None) -> int:
        s = settings if settings is not None else self.store.get()
        panels = s.get("panels", DEFAULT_PANELS)
        seen: set[str] = set()
        for p in panels:
            if not isinstance(p, dict):
                continue
            t = str(p.get("type") or p.get("provider") or "cursor")
            if t in ("cursor", "codex", "qoder"):
                seen.add(t)
        return len(seen)

    def _float_rail_height(self, settings: dict | None = None) -> int:
        n = self._float_panel_type_count(settings)
        item_block = 47
        return 24 + n * item_block + max(0, n - 1) * 10

    def _float_expanded_size(self, settings: dict | None = None) -> tuple[int, int]:
        rail_h = self._float_rail_height(settings)
        # 左侧用量卡约 300 高、圆角 36，窗口必须高于卡片，否则上沿会被 overflow 裁成直角
        return (FLOAT_EXPANDED_WIDTH, max(rail_h + 48, 400))

    def _float_expand(self, expanded: bool) -> None:
        if not self.float_win:
            return
        w, h = self._float_expanded_size() if expanded else FLOAT_COLLAPSED
        try:
            x = self.float_win.x
            y = self.float_win.y
            # 展开向左扩展，收起向右收回
            dw = FLOAT_EXPANDED_WIDTH - FLOAT_COLLAPSED[0]
            if expanded:
                x = max(0, x - dw)
            else:
                x = x + dw
            self.float_win.resize(w, h)
            self.float_win.move(int(x), int(y))
            self.store.save({"floatX": int(x), "floatY": int(y), "floatCollapsed": not expanded})
            self._sync_float_native_material()
        except Exception:
            pass

    def _float_move_by(self, dx: float, dy: float) -> None:
        if not self.float_win:
            return
        if self.float_dock.move_by(dx, dy):
            return
        try:
            x = int(self.float_win.x + dx)
            y = int(self.float_win.y + dy)
            self.float_win.move(x, y)
            self.store.save({"floatX": x, "floatY": y})
        except Exception:
            pass

    def _float_size(self, settings: dict | None = None) -> tuple[int, int]:
        s = settings if settings is not None else self.store.get()
        collapsed = bool(s.get("floatCollapsed", False))
        return FLOAT_COLLAPSED if collapsed else self._float_expanded_size(s)

    def _clamp_float_xy(self, x: int, y: int, w: int, h: int) -> tuple[int, int]:
        margin = 8
        try:
            scr = webview.screens[0]
            sw, sh = int(scr.width), int(scr.height)
        except Exception:
            sw, sh = 1440, 900
        max_x = max(margin, sw - w - margin)
        max_y = max(margin, sh - h - margin)
        return min(max(int(x), margin), max_x), min(max(int(y), margin), max_y)

    def _place_float_window(self, settings: dict | None = None) -> None:
        if not self.float_win:
            return
        s = settings if settings is not None else self.store.get()
        fw, fh = self._float_size(s)
        fx = s.get("floatX")
        fy = s.get("floatY")
        if fx is None or fy is None:
            try:
                scr = webview.screens[0]
                fx = int(scr.width - fw - 16)
                fy = max(40, (int(scr.height) - fh) // 2)
            except Exception:
                fx, fy = 1200, 300
        nx, ny = self._clamp_float_xy(int(fx), int(fy), fw, fh)
        try:
            self.float_win.resize(fw, fh)
            self.float_win.move(nx, ny)
            if bool(s.get("showFloat", True)) and self._float_ready:
                self.float_win.show()
            else:
                self.float_win.hide()
            if nx != fx or ny != fy or fx is None or fy is None:
                self.store.save({"floatX": nx, "floatY": ny})
        except Exception:
            pass

    def _close_login_win(self, *, refresh_on_cancel: bool = False) -> None:
        self._login_poll_stop.set()
        win = self.login_win
        self.login_win = None
        if win:
            try:
                win.destroy()
            except Exception:
                pass
        if refresh_on_cancel and not self._login_done:
            # 关闭网页登录后，回退到本机 Cursor 登录态再同步一次
            threading.Thread(target=lambda: self.bridge.refresh_usage(True), daemon=True).start()

    def _finish_login(self, token: str) -> None:
        self._login_done = True
        self.store.save({"manualToken": token})
        self._close_login_win(refresh_on_cancel=False)
        self._show_main()
        try:
            if self.main_win and "dashboard" not in (self.main_win.get_current_url() or ""):
                self._navigate("dashboard")
        except Exception:
            self._navigate("dashboard")
        threading.Thread(target=lambda: self.bridge.refresh_usage(True), daemon=True).start()

    def _read_login_cookie(self, win) -> str | None:
        try:
            token = _extract_session_token(win.get_cookies())
            if token:
                return token
        except Exception:
            pass
        # 部分平台 HttpOnly Cookie 读不到时，尝试从 URL 判断是否已进站，再跳到同域页重读
        try:
            url = (win.get_current_url() or "").lower()
        except Exception:
            url = ""
        if "cursor.com" in url and any(
            x in url for x in ("/dashboard", "/settings", "/agents", "/usage", "/cn/")
        ):
            try:
                # 再取一次；若仍空，引导到 settings 以稳定同域 Cookie
                token = _extract_session_token(win.get_cookies())
                if token:
                    return token
                if "/settings" not in url:
                    win.load_url("https://www.cursor.com/settings")
            except Exception:
                pass
        return None

    def _poll_login_cookie(self) -> None:
        redirected = False
        while not self._login_poll_stop.is_set() and not self._quitting:
            win = self.login_win
            if not win:
                break
            try:
                token = self._read_login_cookie(win)
                if token:
                    self._finish_login(token)
                    return
                url = (win.get_current_url() or "").lower()
                if (not redirected) and "cursor.com" in url and any(
                    x in url for x in ("/dashboard", "/settings", "/agents", "/usage")
                ):
                    redirected = True
                    try:
                        win.load_url("https://www.cursor.com/settings")
                    except Exception:
                        pass
            except Exception:
                pass
            if self._login_poll_stop.wait(1.2):
                break

    def login_status(self) -> dict:
        return {
            "open": self.login_win is not None,
            "done": bool(self._login_done),
        }

    def _open_login(self) -> dict:
        """打开 Cursor 网页登录窗口，登录成功后自动保存 Session Token。"""
        with self._login_lock:
            if self.login_win:
                try:
                    self.login_win.show()
                    self.login_win.restore()
                    return {"ok": True, "alreadyOpen": True}
                except Exception:
                    self.login_win = None

            self._login_poll_stop.clear()
            self._login_done = False
            try:
                self.login_win = webview.create_window(
                    title="登录 Cursor",
                    url=LOGIN_URL,
                    width=980,
                    height=720,
                    background_color="#ffffff",
                )
            except Exception as exc:
                return {"ok": False, "error": str(exc)}

            def handle_login_closing():
                was_done = self._login_done
                self.login_win = None
                self._login_poll_stop.set()
                if not was_done:
                    threading.Thread(
                        target=lambda: self.bridge.refresh_usage(True), daemon=True
                    ).start()
                return True

            try:
                self.login_win.events.closing += handle_login_closing
            except Exception:
                pass

            threading.Thread(target=self._poll_login_cookie, daemon=True).start()
            return {"ok": True, "alreadyOpen": False}

    def _handle_main_closing(self) -> bool:
        if self._quitting:
            return True
        self._quit()
        # _quit queues destruction of all windows. Cancel this initial close
        # so the main window is closed exactly once by that shared path.
        return False

    def _quit(self) -> None:
        if self._quitting:
            return
        self._quitting = True
        self._refresh_stop.set()
        self._login_poll_stop.set()
        for controller in (self.main_native, self.float_native, self.float_pointer, self.float_dock):
            try:
                controller.dispose()
            except Exception:
                pass
        self._close_login_win()
        if self._ui_server:
            try:
                self._ui_server.shutdown()
                self._ui_server.server_close()
            except Exception:
                pass
        if self._tray:
            def hide_tray() -> None:
                self._tray.visible = False

            if sys.platform == "darwin":
                # pystray.stop() would stop the shared AppKit loop before
                # pywebview's queued window destruction has run.
                _run_on_main(hide_tray)
            else:
                self._tray.stop()
        for win in list(webview.windows):
            try:
                win.destroy()
            except Exception:
                pass

    def _start_tray(self) -> None:
        try:
            import pystray
            from PIL import Image
        except ImportError:
            return

        icon_path = ASSETS / "tray.png"
        if not icon_path.exists():
            icon_path = ASSETS / "icon.png"
        image = Image.open(icon_path) if icon_path.exists() else Image.new("RGB", (32, 32), (59, 130, 246))

        def on_open(icon, item):  # noqa: ARG001
            self._navigate("panels")

        def on_detail(icon, item):  # noqa: ARG001
            self._navigate("dashboard")

        def on_refresh(icon, item):  # noqa: ARG001
            threading.Thread(target=lambda: self.bridge.refresh_usage(True), daemon=True).start()

        def on_quit(icon, item):  # noqa: ARG001
            self._quit()

        menu = pystray.Menu(
            pystray.MenuItem("打开模型额度", on_open),
            pystray.MenuItem("Cursor 用量详情", on_detail),
            pystray.MenuItem("立即刷新", on_refresh),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", on_quit),
        )
        def start() -> None:
            if self._quitting:
                return
            self._tray = pystray.Icon("seeUtoken", image, "seeUtoken · Cursor 用量", menu)
            if sys.platform == "darwin":
                # Share pywebview's AppKit loop instead of starting another one.
                def setup(icon):
                    _run_on_main(lambda: setattr(icon, "visible", not self._quitting))

                self._tray.run_detached(setup=setup)
            else:
                threading.Thread(target=self._tray.run, daemon=True).start()

        if sys.platform == "darwin":
            _run_on_main(start)
        else:
            start()

    def _auto_refresh_loop(self) -> None:
        while not self._refresh_stop.is_set():
            minutes = int(self.store.get().get("autoRefreshMinutes") or 5)
            # 0 = 仅手动刷新；短睡后重读配置
            if minutes <= 0:
                if self._refresh_stop.wait(30):
                    break
                continue
            if self._refresh_stop.wait(max(1, minutes) * 60):
                break
            try:
                self.bridge.refresh_usage(True)
            except Exception:
                pass

    def run(self) -> None:
        settings = self.store.get()
        screen = webview.screens[0] if getattr(webview, "screens", None) else None

        # 先起本机 UI 服务、再写 bootstrap，最后开窗口（避开 file:// 白屏）
        self._start_ui_server()
        self._inject_panels_bootstrap()
        self._inject_float_bootstrap()

        fw, fh = self._float_size(settings)
        fx = settings.get("floatX")
        fy = settings.get("floatY")
        if fx is None:
            fx = 1200
        if fy is None:
            fy = 300
        fx, fy = self._clamp_float_xy(int(fx), int(fy), fw, fh)

        self.main_win = webview.create_window(
            title="seeUtoken · 模型额度",
            url=self._page("panels"),
            width=1200,
            height=860,
            min_size=(900, 640),
            background_color="#f5f7f9" if settings.get("floatGlassStyle") == "light" else "#111824",
            transparent=sys.platform == "darwin",
            js_api=self.bridge,
            hidden=False,
        )

        self.float_win = webview.create_window(
            title="seeUtoken float",
            url=self._page("float"),
            width=fw,
            height=fh,
            x=int(fx),
            y=int(fy),
            frameless=True,
            # 固定悬浮窗尺寸，禁止从透明边缘拉伸导致玻璃轮廓与点击区域错位。
            resizable=False,
            on_top=bool(settings.get("floatAlwaysOnTop", True)),
            transparent=True,
            easy_drag=False,
            js_api=self.float_bridge,
            hidden=True,
        )
        self.float_native.attach(self.float_win)
        self.main_native.attach(self.main_win)

        def push_heatmap(payload: dict) -> None:
            # 热力只推主窗口；体积大时 evaluate_js 也可能失败，失败不影响额度卡
            self._eval_push(self.main_win, payload, "__seeUtokenHeatmapPush")

        self.bridge.bind(
            on_navigate=self._navigate,
            on_float_expand=self._float_expand,
            on_float_move=self._float_move_by,
            on_quit=self._quit,
            on_hide_main=self._hide_main,
            on_show_float=self._set_float_visible,
            on_login=self._open_login,
            login_status=self.login_status,
            broadcast=self._broadcast,
            on_heatmap=push_heatmap,
            on_settings_saved=self._sync_appearance,
        )

        def on_started():
            self._install_macos_lifecycle()
            self._place_float_window(settings)
            self._start_tray()
            threading.Thread(target=lambda: self.bridge.refresh_usage(True), daemon=True).start()
            threading.Thread(target=self._auto_refresh_loop, daemon=True).start()

            def boot_push():
                for delay in (0.4, 1.0, 2.0):
                    time.sleep(delay)
                    try:
                        self._push_card()
                    except Exception:
                        pass

            threading.Thread(target=boot_push, daemon=True).start()

            def load_watchdog():
                time.sleep(2.0)
                if not self._main_loaded and self.main_win:
                    print("[seeUtoken] main load watchdog retry", flush=True)
                    try:
                        self.main_win.load_url(self._page("panels"))
                    except Exception:
                        pass
                if not self._float_loaded and self.float_win:
                    print("[seeUtoken] float load watchdog retry", flush=True)
                    try:
                        self.float_win.load_url(self._page("float"))
                    except Exception:
                        pass

            threading.Thread(target=load_watchdog, daemon=True).start()

        def handle_main_loaded():
            self._main_loaded = True
            print("[seeUtoken] main page loaded", flush=True)

            def after_loaded():
                self._sync_main_appearance()
                try:
                    r = self.main_win.evaluate_js(
                        "(document.querySelector('.quota-home')?'HOME':'EMPTY')"
                        "+ ' app=' + (document.querySelector('#app')?.innerHTML||'').slice(0,40)"
                    )
                    print(f"[seeUtoken] main dom probe: {r}", flush=True)
                except Exception as exc:
                    print(f"[seeUtoken] main dom probe failed: {exc}", flush=True)
                for delay in (0.25, 0.8, 1.6):
                    time.sleep(delay)
                    try:
                        self._push_card()
                    except Exception:
                        pass

            threading.Thread(target=after_loaded, daemon=True).start()

        def handle_float_closing():
            if self._quitting:
                return True
            # 误点关闭时只隐藏，避免悬浮窗被销毁后无法找回
            try:
                self.float_dock.set_visible(False)
                self.float_win.hide()
                self.store.save({"showFloat": False})
            except Exception:
                pass
            return False

        def handle_float_loaded():
            self._float_loaded = True
            self.float_pointer.attach(self.float_win)
            self.float_dock.attach(self.float_win)
            print("[seeUtoken] float page loaded", flush=True)

            # loaded 事件在主线程触发；pywebview 的 evaluate_js 在主线程会自死锁，
            # 所以同步与 DOM 探针都放到后台线程
            def after_loaded():
                try:
                    self._sync_float_native_material()
                except Exception:
                    pass
                try:
                    r = self.float_win.evaluate_js(
                        "document.visibilityState + ' | rail=' + (document.querySelector('.rail')?'Y':'N')"
                        " + ' | rect=' + JSON.stringify(document.querySelector('.rail')?.getBoundingClientRect()||null)"
                    )
                    print(f"[seeUtoken] float dom probe: {r}", flush=True)
                except Exception as exc:
                    print(f"[seeUtoken] float dom probe failed: {exc}", flush=True)
                try:
                    from webview.platforms.cocoa import BrowserView

                    bv = BrowserView.get_instance("pywebview_window", self.float_win)
                    ns = bv.window if bv else None
                    if ns is not None:
                        print(
                            f"[seeUtoken] float window: visible={bool(ns.isVisible())} "
                            f"occlusion={int(ns.occlusionState())} "
                            f"alpha={float(ns.alphaValue())} "
                            f"level={int(ns.level())}",
                            flush=True,
                        )
                except Exception as exc:
                    print(f"[seeUtoken] float window probe failed: {exc}", flush=True)

            threading.Thread(target=after_loaded, daemon=True).start()

        try:
            self.main_win.events.loaded += handle_main_loaded
            self.float_win.events.loaded += handle_float_loaded
        except Exception:
            pass
        self.main_win.events.closing += self._handle_main_closing
        self.float_win.events.closing += handle_float_closing

        gui = "edgechromium" if sys.platform == "win32" else None
        # private_mode=False 才能稳定读取登录 Cookie
        try:
            webview.start(func=on_started, gui=gui, debug=False, private_mode=False)
        finally:
            self._quit()
            if self._tray:
                self._tray.stop()


def main() -> None:
    SeeUtokenApp().run()


if __name__ == "__main__":
    main()
