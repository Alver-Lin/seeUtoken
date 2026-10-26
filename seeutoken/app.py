"""seeUtoken 桌面应用：主窗口 + 置顶悬浮球 + 托盘。"""

from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

import webview

from .bridge import AppBridge
from .storage import SettingsStore

ROOT = Path(__file__).resolve().parent.parent
UI = ROOT / "ui"
ASSETS = ROOT / "assets"

FLOAT_COLLAPSED = (72, 72)
FLOAT_EXPANDED = (360, 420)


def _file_uri(path: Path) -> str:
    return path.resolve().as_uri()


class SeeUtokenApp:
    def __init__(self) -> None:
        self.store = SettingsStore()
        self.bridge = AppBridge(self.store)
        self.main_win: webview.Window | None = None
        self.float_win: webview.Window | None = None
        self._tray = None
        self._refresh_stop = threading.Event()
        self._quitting = False

    def _page(self, name: str) -> str:
        return _file_uri(UI / name / "index.html")

    def _broadcast(self, payload: dict) -> None:
        js = f"window.__seeUtokenPush && window.__seeUtokenPush({json.dumps(payload, ensure_ascii=False)})"
        for win in (self.main_win, self.float_win):
            if not win:
                continue
            try:
                win.evaluate_js(js)
            except Exception:
                pass

    def _navigate(self, page: str) -> None:
        if not self.main_win:
            return
        url = self._page("dashboard" if page == "dashboard" else "panels")
        title = "seeUtoken · Cursor 用量" if page == "dashboard" else "seeUtoken · 模型额度"
        try:
            self.main_win.set_title(title)
            self.main_win.load_url(url)
            self.main_win.show()
            self.main_win.restore()
        except Exception:
            pass

    def _hide_main(self) -> None:
        if self.main_win:
            try:
                self.main_win.hide()
            except Exception:
                pass

    def _show_main(self) -> None:
        if self.main_win:
            try:
                self.main_win.show()
                self.main_win.restore()
            except Exception:
                pass

    def _set_float_visible(self, visible: bool) -> None:
        if not self.float_win:
            return
        try:
            if visible:
                self.float_win.show()
            else:
                self.float_win.hide()
        except Exception:
            pass

    def _float_expand(self, expanded: bool) -> None:
        if not self.float_win:
            return
        w, h = FLOAT_EXPANDED if expanded else FLOAT_COLLAPSED
        try:
            x = self.float_win.x
            y = self.float_win.y
            # 展开向左扩展，收起向右收回
            dw = FLOAT_EXPANDED[0] - FLOAT_COLLAPSED[0]
            if expanded:
                x = max(0, x - dw)
            else:
                x = x + dw
            self.float_win.resize(w, h)
            self.float_win.move(int(x), int(y))
            self.store.save({"floatX": int(x), "floatY": int(y), "floatCollapsed": not expanded})
        except Exception:
            pass

    def _float_move_by(self, dx: float, dy: float) -> None:
        if not self.float_win:
            return
        try:
            x = int(self.float_win.x + dx)
            y = int(self.float_win.y + dy)
            self.float_win.move(x, y)
            self.store.save({"floatX": x, "floatY": y})
        except Exception:
            pass

    def _quit(self) -> None:
        if self._quitting:
            return
        self._quitting = True
        self._refresh_stop.set()
        if self._tray:
            try:
                self._tray.stop()
            except Exception:
                pass
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
            self._show_main()
            self._navigate("panels")

        def on_detail(icon, item):  # noqa: ARG001
            self._show_main()
            self._navigate("dashboard")

        def on_refresh(icon, item):  # noqa: ARG001
            threading.Thread(target=lambda: self.bridge.refresh_usage(True), daemon=True).start()

        def on_toggle_float(icon, item):  # noqa: ARG001
            show = not bool(self.store.get().get("showFloat", True))
            self.store.save({"showFloat": show})
            self._set_float_visible(show)

        def on_quit(icon, item):  # noqa: ARG001
            self._quit()

        menu = pystray.Menu(
            pystray.MenuItem("打开模型额度", on_open),
            pystray.MenuItem("Cursor 用量详情", on_detail),
            pystray.MenuItem("立即刷新", on_refresh),
            pystray.MenuItem("显示/隐藏悬浮球", on_toggle_float),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", on_quit),
        )
        self._tray = pystray.Icon("seeUtoken", image, "seeUtoken · Cursor 用量", menu)
        threading.Thread(target=self._tray.run, daemon=True).start()

    def _auto_refresh_loop(self) -> None:
        while not self._refresh_stop.is_set():
            minutes = max(1, int(self.store.get().get("autoRefreshMinutes") or 5))
            if self._refresh_stop.wait(minutes * 60):
                break
            try:
                self.bridge.refresh_usage(True)
            except Exception:
                pass

    def run(self) -> None:
        settings = self.store.get()
        screen = webview.screens[0] if getattr(webview, "screens", None) else None

        # 先创建占位，screens 在 start 前可能为空；用默认位置
        fw = FLOAT_COLLAPSED[0] if settings.get("floatCollapsed", True) else FLOAT_EXPANDED[0]
        fh = FLOAT_COLLAPSED[1] if settings.get("floatCollapsed", True) else FLOAT_EXPANDED[1]
        fx = settings.get("floatX")
        fy = settings.get("floatY")
        if fx is None:
            fx = 1200
        if fy is None:
            fy = 300

        self.main_win = webview.create_window(
            title="seeUtoken · 模型额度",
            url=self._page("panels"),
            width=1200,
            height=860,
            min_size=(900, 640),
            background_color="#f3f5f8",
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
            on_top=True,
            transparent=True,
            easy_drag=False,
            js_api=self.bridge,
            hidden=not bool(settings.get("showFloat", True)),
        )

        self.bridge.bind(
            on_navigate=self._navigate,
            on_float_expand=self._float_expand,
            on_float_move=self._float_move_by,
            on_quit=self._quit,
            on_hide_main=self._hide_main,
            on_show_float=self._set_float_visible,
            broadcast=self._broadcast,
        )

        def on_started():
            # 纠正悬浮球初始位置到屏幕右侧
            try:
                if settings.get("floatX") is None and self.float_win:
                    # screens available after start
                    scr = webview.screens[0]
                    x = scr.width - fw - 16
                    y = max(40, (scr.height - fh) // 2)
                    self.float_win.move(x, y)
                    self.store.save({"floatX": x, "floatY": y})
            except Exception:
                pass

            self._start_tray()
            threading.Thread(target=lambda: self.bridge.refresh_usage(True), daemon=True).start()
            threading.Thread(target=self._auto_refresh_loop, daemon=True).start()

        # 关闭主窗口时隐藏而非退出；悬浮球不允许直接关掉
        def handle_main_closing():
            if self._quitting:
                return True
            self._hide_main()
            return False

        def handle_float_closing():
            return bool(self._quitting)

        self.main_win.events.closing += handle_main_closing
        self.float_win.events.closing += handle_float_closing

        gui = "edgechromium" if sys.platform == "win32" else None
        webview.start(func=on_started, gui=gui, debug=False)


def main() -> None:
    SeeUtokenApp().run()


if __name__ == "__main__":
    main()
