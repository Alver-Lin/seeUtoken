"""悬浮窗原生材质：异形 Liquid Glass / HUD Vibrancy（参考 token-monitor nativeMaterialVisibility.js + edgeDock/controller.js）。"""

from __future__ import annotations

import os
import sys
from typing import Any

from .mac_liquid_glass import MacLiquidGlass, liquid_glass_supported
from .storage import is_light_appearance, is_liquid_glass_style, normalize_float_glass_style


def _run_on_main(block) -> None:
    """AppKit 只能在主线程操作；pyobjc 选择子是 addOperationWithBlock_。"""
    try:
        from Foundation import NSThread

        if NSThread.isMainThread():
            block()
            return
    except Exception:
        pass
    try:
        from Foundation import NSOperationQueue

        NSOperationQueue.mainQueue().addOperationWithBlock_(block)
        return
    except Exception:
        pass
    block()


def _ns_window_for(pywebview_window: Any) -> Any | None:
    if sys.platform != "darwin" or not pywebview_window:
        return None
    try:
        from webview.platforms.cocoa import BrowserView

        bv = BrowserView.get_instance("pywebview_window", pywebview_window)
        return bv.window if bv else None
    except Exception:
        return None


def _reduce_transparency() -> bool:
    try:
        from AppKit import NSWorkspace

        return bool(
            NSWorkspace.sharedWorkspace().accessibilityDisplayShouldReduceTransparency()
        )
    except Exception:
        return False


def _fix_webview_transparency(ns_window: Any) -> None:
    """macOS 26 上 _setDrawsTransparentBackground: 已失效，WKWebView 会画成不透明白底。
    现代替代 API 是 underPageBackgroundColor（macOS 13.3+），置为透明色。"""
    try:
        from AppKit import NSColor
        from WebKit import WKWebView
    except Exception:
        return

    def walk(view):
        if view is None:
            return None
        try:
            if view.isKindOfClass_(WKWebView):
                return view
        except Exception:
            pass
        try:
            for sub in view.subviews():
                found = walk(sub)
                if found is not None:
                    return found
        except Exception:
            pass
        return None

    try:
        webview = walk(ns_window.contentView())
        if webview is None:
            print("[seeUtoken] transparency fix: WKWebView not found", flush=True)
            return
        clear = NSColor.clearColor()
        try:
            webview.setValue_forKey_(clear, "underPageBackgroundColor")
            print("[seeUtoken] underPageBackgroundColor -> clear", flush=True)
        except Exception as exc:
            print(f"[seeUtoken] underPageBackgroundColor failed: {exc}", flush=True)
        # 旧接口在新系统上已无效，但留着兼容老 macOS
        try:
            webview.setValue_forKey_(True, "drawsTransparentBackground")
        except Exception:
            pass
        try:
            layer = webview.layer()
            if layer is not None:
                layer.setOpaque_(False)
        except Exception:
            pass
    except Exception:
        pass


def _style_from_settings(settings: dict) -> tuple[str, float]:
    """返回 (glass_style, tint_opacity 0..1)。"""
    mode = normalize_float_glass_style(settings.get("floatGlassStyle"))
    if mode == "liquid-light":
        return "regular", 0.12
    if mode == "liquid-light-clear":
        return "clear", 0.24
    if mode == "liquid":
        return "regular", 0.0
    if mode == "liquid-clear":
        # token-monitor：Clear 默认 0.35 黑 tint，保证文字对比度
        return "clear", 0.35
    return "regular", 0.0


def _material_type(entry: dict) -> str:
    if entry.get("opaque"):
        return "opaque"
    if entry.get("reduced_transparency"):
        return "opaque"
    if entry.get("glass") is not None:
        return "liquid-glass"
    if entry.get("vibrancy") is not None:
        return "vibrancy"
    return "transparent"


class FloatNativeMaterialController:
    def __init__(self, on_ready=None) -> None:
        self._win: Any | None = None
        self._glass: MacLiquidGlass | None = None
        self._vibrancy: Any | None = None
        self._glass_failed: str | None = None
        self._shape: dict | None = None
        self._on_ready = on_ready
        self._synced = False
        self._ready_notified = False
        self._material_config = None
        self._glass_params: dict[str, Any] = {
            "dark": True,
            "radius": 16,
            "visible": True,
            "style": "regular",
            "tint_opacity": 0.0,
        }
        self._state: dict[str, Any] = {
            "type": "transparent",
            "reducedTransparency": False,
            "highContrast": False,
            "fallbackReason": None,
            "liquidGlassSupported": liquid_glass_supported(),
        }

    def get_state(self) -> dict[str, Any]:
        return dict(self._state)

    def attach(self, pywebview_window: Any) -> None:
        self._win = pywebview_window

    def _notify_ready(self) -> None:
        # Both events may arrive first: AppKit initialization or the first DOM geometry.
        if self._synced and self._shape is not None and not self._ready_notified:
            self._ready_notified = True
            if self._on_ready:
                self._on_ready()

    def update_shape(self, payload: dict | None) -> None:
        """前端上报的悬浮窗轮廓（rail 胶囊 + pop 卡片尾巴），驱动异形玻璃。"""
        if not isinstance(payload, dict):
            return
        commands = payload.get("commands")
        if not isinstance(commands, list) or not commands:
            return
        self._shape = {
            "commands": commands,
            "width": float(payload.get("width") or 0),
            "height": float(payload.get("height") or 0),
            "collapsed": bool(payload.get("collapsed")),
        }

        def work() -> None:
            try:
                # Compact handle is a plain rectangle; native glass would add
                # a pill-shaped edge and highlights around it.
                if self._glass is not None:
                    self._glass_params["visible"] = not self._shape.get("collapsed", False)
                    self._glass.update(shape=self._shape, **self._glass_params)
            except Exception:
                pass
            self._notify_ready()

        if sys.platform == "darwin":
            _run_on_main(work)
        else:
            if sys.platform == "win32":
                from .windows_float import apply_sidebar

                apply_sidebar(self._win, self._state.get("floatStyle", "light"), self._shape)
            work()

    def sync(self, settings: dict | None = None, on_complete=None) -> dict[str, Any]:
        settings = settings or {}
        mode = normalize_float_glass_style(settings.get("floatGlassStyle"))
        if sys.platform != "darwin":
            self._state["floatStyle"] = mode
            if sys.platform == "win32":
                from .windows_float import apply_sidebar

                self._state["type"] = "opaque"
                self._state.update(apply_sidebar(self._win, mode, self._shape) or {})
            self._synced = True
            if on_complete:
                on_complete()
            self._notify_ready()
            return self.get_state()

        reduced = _reduce_transparency()
        supported = liquid_glass_supported()
        # Liquid 模式：整窗 NSGlassEffectView 按前端上报的轮廓成型（token-monitor
        # edgeDock 同款）；rail/pop 两种观感靠 style/tint 区分，不再各叠 CSS 材质
        use_window_liquid = (
            is_liquid_glass_style(mode)
            and os.environ.get("SEEU_FLOAT_NATIVE_GLASS") != "0"
        )

        def work() -> None:
            ns = _ns_window_for(self._win)
            if not ns:
                return
            config = (ns, mode, reduced, supported, use_window_liquid)
            if self._synced and self._material_config == config:
                if on_complete:
                    on_complete()
                self._notify_ready()
                return
            _fix_webview_transparency(ns)
            self._dispose_glass()
            self._dispose_vibrancy()

            if (
                use_window_liquid
                and not reduced
                and supported
                and not self._glass_failed
            ):
                try:
                    self._glass = MacLiquidGlass(ns, shaped=True)
                    g_style, tint = _style_from_settings(settings)
                    self._glass_params = {
                        "dark": not is_light_appearance(mode),
                        "radius": 16,
                        # 轮廓未上报前先隐藏，避免整窗矩形玻璃一闪而过
                        "visible": self._shape is not None and not self._shape.get("collapsed", False),
                        "style": "clear" if g_style == "clear" else "regular",
                        "tint_opacity": tint,
                    }
                    self._glass.update(shape=self._shape, **self._glass_params)
                    self._glass_params["visible"] = not bool((self._shape or {}).get("collapsed"))
                except Exception as exc:
                    self._glass_failed = str(exc)
                    self._dispose_glass()

            entry = {
                "glass": self._glass,
                "vibrancy": self._vibrancy,
                "reduced_transparency": reduced,
                "opaque": reduced,
            }
            self._state = {
                "floatStyle": mode,
                "type": _material_type(entry),
                "reducedTransparency": reduced,
                "highContrast": False,
                "fallbackReason": self._glass_failed,
                "liquidGlassSupported": supported,
            }
            self._material_config = config
            self._synced = True
            if on_complete:
                on_complete()
            self._notify_ready()

        _run_on_main(work)
        return self.get_state()

    def push_to_webview(self, evaluate_js: Any, on_applied=None) -> None:
        """推送原生材质状态到前端。

        pywebview 的 evaluate_js 会 callAfter + 信号量等待：在主线程调用即自死锁。
        这里不需要返回值，直接 fire-and-forget，任何线程调用都安全。"""
        if not self._win:
            return
        import json

        payload = json.dumps(self.get_state(), ensure_ascii=False)
        js = (
            f"window.__seeUtokenNativeMaterial={payload};"
            "if(typeof window.__seeUtokenApplyNativeMaterial==='function')"
            "{window.__seeUtokenApplyNativeMaterial(window.__seeUtokenNativeMaterial);}"
        )

        if sys.platform != "darwin":
            evaluate_js(self._win, js)
            if on_applied:
                on_applied()
            return

        try:
            from PyObjCTools import AppHelper
            from webview.platforms.cocoa import BrowserView

            bv = BrowserView.get_instance("pywebview_window", self._win)
            wv = getattr(bv, "webview", None) if bv else None
            if wv is None:
                return

            def run() -> None:
                try:
                    def applied(result, error):
                        if error:
                            print(f"[seeUtoken] native material state failed: {error}", flush=True)
                        elif on_applied:
                            on_applied()

                    wv.evaluateJavaScript_completionHandler_(js, applied)
                except Exception as exc:
                    print(f"[seeUtoken] native material state failed: {exc}", flush=True)

            AppHelper.callAfter(run)
        except Exception:
            pass

    def _ensure_vibrancy(self, ns_window: Any) -> None:
        from AppKit import (
            NSVisualEffectBlendingModeBehindWindow,
            NSVisualEffectMaterialHUDWindow,
            NSVisualEffectStateActive,
            NSViewHeightSizable,
            NSViewWidthSizable,
            NSWindowBelow,
        )

        content = ns_window.contentView()
        if not content:
            return
        bounds = content.bounds()
        view = self._vibrancy
        if view is None:
            from AppKit import NSVisualEffectView

            view = NSVisualEffectView.alloc().init()
            view.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
            view.setWantsLayer_(True)
            view.setState_(NSVisualEffectStateActive)
            view.setBlendingMode_(NSVisualEffectBlendingModeBehindWindow)
            view.setMaterial_(NSVisualEffectMaterialHUDWindow)
            content.addSubview_positioned_relativeTo_(view, NSWindowBelow, None)
            self._vibrancy = view
        view.setFrame_(bounds)

    def _dispose_glass(self) -> None:
        if self._glass:
            try:
                self._glass.dispose()
            except Exception:
                pass
        self._glass = None

    def _dispose_vibrancy(self) -> None:
        view = self._vibrancy
        self._vibrancy = None
        if view:
            try:
                view.removeFromSuperview()
            except Exception:
                pass

    def dispose(self) -> None:
        def work() -> None:
            self._dispose_glass()
            self._dispose_vibrancy()

        _run_on_main(work)
