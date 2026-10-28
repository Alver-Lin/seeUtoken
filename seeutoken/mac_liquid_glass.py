"""macOS NSGlassEffectView（与 token-monitor macLiquidGlass.js 行为对齐，含 _setPath: 异形）。"""

from __future__ import annotations

import json
import sys
from typing import Any, Literal, Sequence

GlassStyle = Literal["regular", "clear"]

_SET_PATH_SEL = "_setPath:"


def liquid_glass_supported() -> bool:
    if sys.platform != "darwin":
        return False
    try:
        import platform

        major = int(str(platform.mac_ver()[0] or "0").split(".")[0])
        if major >= 26:
            return True
        rel = platform.release().split(".")[0]
        return int(rel) >= 25
    except Exception:
        return False


def _glass_class():
    from AppKit import NSGlassEffectView

    return NSGlassEffectView


def _glass_path_supported() -> bool:
    """_setPath: 是私有 setter（系统玻璃自用的任意轮廓接口）；先探测，缺失则回退。"""
    try:
        from Foundation import NSSelectorFromString

        return bool(
            _glass_class().instancesRespondToSelector_(
                NSSelectorFromString(_SET_PATH_SEL)
            )
        )
    except Exception:
        return False


def _build_cg_path(commands: Sequence[Sequence[Any]], height: float):
    """shape 命令是自上而下坐标（M/L/C/Z）；layer 自下而上，逐点翻转 y。"""
    import Quartz

    path = Quartz.CGPathCreateMutable()
    for cmd in commands:
        op, *p = cmd
        if op == "M":
            Quartz.CGPathMoveToPoint(path, None, float(p[0]), height - float(p[1]))
        elif op == "L":
            Quartz.CGPathAddLineToPoint(path, None, float(p[0]), height - float(p[1]))
        elif op == "C":
            Quartz.CGPathAddCurveToPoint(
                path,
                None,
                float(p[0]),
                height - float(p[1]),
                float(p[2]),
                height - float(p[3]),
                float(p[4]),
                height - float(p[5]),
            )
        elif op == "Z":
            Quartz.CGPathCloseSubpath(path)
    return path


def _without_animation(fn) -> None:
    """形状与材质在同一事务里提交，避免跨两帧的闪烁（token-monitor withoutAnimation）。"""
    try:
        from Quartz import CATransaction

        CATransaction.begin()
        try:
            CATransaction.setDisableActions_(True)
            fn()
        finally:
            CATransaction.commit()
    except Exception:
        fn()


class MacLiquidGlass:
    """在窗口 contentView 下方插入 NSGlassEffectView，不移动 WebKit 层级。"""

    def __init__(self, ns_window: Any, shaped: bool = False) -> None:
        from AppKit import NSViewHeightSizable, NSViewWidthSizable, NSWindowBelow

        self._ns_window = ns_window
        self._disposed = False
        self._last_style: GlassStyle | None = None
        self._last_tint = -1.0
        self._last_dark: bool | None = None
        self._last_radius: float | None = None
        self._last_visible: bool | None = None
        self._last_shape: str | None = None
        self._forced_main = False
        self._original_force_main: bool | None = None

        glass_cls = _glass_class()
        content = ns_window.contentView()
        if content is None:
            raise RuntimeError("Window content view unavailable")

        if shaped and not _glass_path_supported():
            raise RuntimeError("NSGlassEffectView cannot take a custom shape")

        bounds = content.bounds()
        glass = glass_cls.alloc().init()
        if not glass:
            raise RuntimeError("NSGlassEffectView initialization failed")

        if shaped:
            glass.setWantsLayer_(True)

        glass.setFrame_(bounds)
        glass.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
        glass.setStyle_(0)  # NSGlassEffectViewStyleRegular

        # key window 下玻璃会叠一层增亮模糊，洗掉密集文字；subdued 去掉这层，
        # 同时保留窗口激活态阴影（token-monitor 同款私有开关，先探测再用）
        if glass.respondsToSelector_("set_subduedState:"):
            glass.set_subduedState_(1)

        content.addSubview_positioned_relativeTo_(glass, NSWindowBelow, None)
        self._glass = glass

        if ns_window.respondsToSelector_("_forceMainAppearance"):
            self._original_force_main = bool(ns_window._forceMainAppearance())

    def _set_path(self, shape: dict) -> None:
        """玻璃按轮廓自身成型，边缘高光跟着真实路径走（token-monitor setPath）。"""
        key = json.dumps(shape, separators=(",", ":"))
        if key == self._last_shape:
            return
        commands = shape.get("commands") or []
        height = float(shape.get("height") or 0)
        if not commands or height <= 0:
            return
        path = _build_cg_path(commands, height)
        glass = self._glass
        try:
            from Foundation import NSSelectorFromString

            glass.performSelector_withObject_(NSSelectorFromString(_SET_PATH_SEL), path)
        except Exception:
            # 部分 pyobjc 版本 CFType→id 转换失败时，走 libobjc 直发
            import ctypes

            from objc import pyobjc_id

            libobjc = ctypes.CDLL("/usr/lib/libobjc.dylib")
            libobjc.sel_registerName.restype = ctypes.c_void_p
            libobjc.sel_registerName.argtypes = [ctypes.c_char_p]
            libobjc.objc_msgSend.restype = None
            libobjc.objc_msgSend.argtypes = [
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_void_p,
            ]
            sel = libobjc.sel_registerName(b"_setPath:")
            libobjc.objc_msgSend(
                ctypes.c_void_p(pyobjc_id(glass)),
                ctypes.c_void_p(sel),
                ctypes.c_void_p(pyobjc_id(path)),
            )
        self._last_shape = key
        # 窗口阴影按内容 alpha 缓存，形状提交后需要刷新
        try:
            win = glass.window()
            if win is not None:
                win.invalidateShadow()
        except Exception:
            pass

    def _sync_force_main(self, force: bool) -> None:
        win = self._ns_window
        if not win.respondsToSelector_("_setForceMainAppearance:"):
            return
        if self._original_force_main:
            return
        if force == self._forced_main:
            return
        win._setForceMainAppearance_(1 if force else 0)
        self._forced_main = force

    def update(
        self,
        *,
        dark: bool = True,
        radius: float = 16,
        visible: bool = True,
        style: GlassStyle = "regular",
        tint_opacity: float = 0,
        shape: dict | None = None,
    ) -> None:
        if self._disposed:
            return

        from AppKit import NSColor

        glass = self._glass
        next_style: GlassStyle = "clear" if style == "clear" else "regular"

        if next_style != self._last_style:
            glass.setStyle_(1 if next_style == "clear" else 0)
            # subdued Regular 去掉聚焦增亮；subdued Clear 会把通透变成重模糊。
            # 切换 style 时恢复各自状态（token-monitor 同款处理）
            if glass.respondsToSelector_("set_subduedState:"):
                glass.set_subduedState_(0 if next_style == "clear" else 1)
            self._last_style = next_style

        tint = max(0.0, min(1.0, float(tint_opacity)))
        # 失焦的 Regular 会淡化 tint；带 tint 的 Regular 与 Clear 统一外观策略，
        # 只改外观不改真实焦点（token-monitor syncGlassAppearance）
        self._sync_force_main(next_style == "clear" or tint > 0)

        if tint != self._last_tint:
            if tint > 0:
                color = NSColor.colorWithSRGBRed_green_blue_alpha_(0, 0, 0, tint)
                glass.setTintColor_(color)
            elif glass.respondsToSelector_("setTintColor:"):
                from objc import nil

                glass.setTintColor_(nil)
            self._last_tint = tint

        if visible != self._last_visible:
            glass.setHidden_(not visible)
            self._last_visible = visible

        if dark != self._last_dark:
            from AppKit import NSAppearance

            name = "NSAppearanceNameDarkAqua" if dark else "NSAppearanceNameAqua"
            appearance = NSAppearance.appearanceNamed_(name)
            if appearance:
                glass.setAppearance_(appearance)
            self._last_dark = dark

        if shape is not None:
            _without_animation(lambda: self._set_path(shape))
        elif radius != self._last_radius:
            glass.setCornerRadius_(float(radius))
            self._last_radius = radius

    def dispose(self) -> None:
        if self._disposed:
            return
        self._disposed = True
        try:
            self._sync_force_main(False)
        except Exception:
            pass
        glass = getattr(self, "_glass", None)
        if glass:
            try:
                glass.removeFromSuperview()
            except Exception:
                pass
        self._glass = None
