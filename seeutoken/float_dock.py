"""Screen-edge docking. All AppKit work runs on the main thread.

The handle is a separate plain native panel. The WebView keeps its full size,
so revealing it never needs to reflow the page or rebuild its glass geometry.
Geometry uses native screen coordinates (origin at the bottom left).
"""
from __future__ import annotations

import json
import sys
import threading
import time
from dataclasses import dataclass

from .float_native_material import _run_on_main
from .mac_liquid_glass import _build_cg_path


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    width: float
    height: float

    @property
    def right(self):
        return self.x + self.width

    @property
    def top(self):
        return self.y + self.height

    def contains(self, x, y):
        return self.x <= x <= self.right and self.y <= y <= self.top


def edge_for(rail: Rect, screens: list[Rect], threshold=16):
    """Return the closest real display edge near the visible rail."""
    candidates = []
    for screen in screens:
        if rail.top <= screen.y or rail.y >= screen.top:
            continue
        for edge, distance in (("left", abs(rail.x - screen.x)), ("right", abs(rail.right - screen.right))):
            if distance <= threshold:
                candidates.append((distance, edge, screen))
    if not candidates:
        return None, None
    _, edge, screen = min(candidates, key=lambda item: item[0])
    return edge, screen


def snapped_frame(frame: Rect, rail: Rect, edge: str, screen: Rect) -> Rect:
    # Move the whole window so the rail touches the requested edge. The Vue
    # layout puts the rail on the left when docked left, otherwise on the right.
    x = screen.x if edge == "left" else screen.right - frame.width
    y = min(max(frame.y, screen.y), max(screen.y, screen.top - frame.height))
    return Rect(x, y, frame.width, frame.height)


def collapsed_frame(frame: Rect, rail_height: float, edge: str, screen: Rect, width=12) -> Rect:
    height = min(56, rail_height, screen.height)
    y = min(max(frame.y + (frame.height - height) / 2, screen.y), screen.top - height)
    return Rect(screen.x if edge == "left" else screen.right - width, y, width, height)


def _rect(native):
    return Rect(float(native.origin.x), float(native.origin.y), float(native.size.width), float(native.size.height))


_timer_class = None
_overlay_panel_class = None


def _float_panel_class():
    global _overlay_panel_class
    if _overlay_panel_class is None:
        from AppKit import NSPanel

        class SeeUtokenOverlayPanel(NSPanel):
            def canBecomeKeyWindow(self):
                return bool(self.focus)

            def canBecomeMainWindow(self):
                return False

        _overlay_panel_class = SeeUtokenOverlayPanel
    return _overlay_panel_class


def _use_overlay_panel(browser):
    """Keep the same live WebView, hosted by a nonactivating NSPanel.

    A regular application NSWindow can stay behind another app's fullscreen
    Space even with auxiliary collection flags. The compact handle is already
    a panel; use the same window category for the rail and its popup contents.
    """
    from AppKit import (
        NSPanel, NSView, NSColor, NSBackingStoreBuffered,
        NSWindowStyleMaskBorderless, NSWindowStyleMaskNonactivatingPanel,
    )

    old = browser.window
    visible = bool(old.isVisible())
    if old.isKindOfClass_(NSPanel):
        return old, visible
    panel = _float_panel_class().alloc().initWithContentRect_styleMask_backing_defer_(
        old.frame(), NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel,
        NSBackingStoreBuffered, False,
    )
    panel.focus = getattr(old, "focus", True)
    panel.setTitle_(old.title())
    panel.setReleasedWhenClosed_(False)
    panel.setOpaque_(False)
    panel.setBackgroundColor_(NSColor.clearColor())
    panel.setHasShadow_(False)
    panel.setHidesOnDeactivate_(False)
    panel.setBecomesKeyOnlyIfNeeded_(True)
    panel.setAcceptsMouseMovedEvents_(True)
    # Detach the old delegate before closing its shell. Otherwise pywebview
    # would interpret that close as destruction of the shared live WebView.
    delegate, content = old.delegate(), old.contentView()
    old.setDelegate_(None)
    old.setContentView_(NSView.alloc().initWithFrame_(content.bounds()))
    panel.setContentView_(content)
    browser.window = panel
    browser.pywebview_window.native = panel
    panel.setDelegate_(delegate)
    old.orderOut_(None)
    old.close()
    return panel, visible


def _timer_target_class():
    global _timer_class
    if _timer_class is None:
        from Foundation import NSObject

        class SeeUtokenFloatDockTimer(NSObject):
            def tick_(self, timer):
                if self.controller is not None:
                    self.controller.tick()

        _timer_class = SeeUtokenFloatDockTimer
    return _timer_class


class FloatDockController:
    HIDE_DELAY = 0.65

    def __init__(self, persist=None, settings=None):
        self._window = self._view = self._timer = self._target = None
        self._persist = persist
        self._edge = None
        self._screen = None
        self._expanded = None
        self._collapsed = False
        self._dragging = False
        self._moved = False
        self._hide_at = None
        self._geometry = None
        self._input_path = None
        self._mouse_passthrough = None
        self._last_pointer = None
        self._waiting_until = 0
        self._saved = None
        self._handle = None
        self._enabled = True
        self._transition = 0
        self._animating_until = 0
        self._auto_hide = (settings or {}).get("floatAutoHide", True) is not False
        self._always_on_top = (settings or {}).get("floatAlwaysOnTop", True) is not False

    def _order_panel(self, panel):
        if self._always_on_top:
            panel.orderFrontRegardless()
        else:
            # Lowering the level alone leaves an already-frontmost panel in
            # front until the user activates another window. Apply the choice
            # immediately, including after showing or revealing the rail.
            panel.orderBack_(None)

    def _apply_window_policy(self):
        from AppKit import (
            NSNormalWindowLevel, NSStatusWindowLevel,
            NSWindowCollectionBehaviorCanJoinAllSpaces,
            NSWindowCollectionBehaviorFullScreenAuxiliary,
            NSWindowCollectionBehaviorMoveToActiveSpace,
        )

        level = NSStatusWindowLevel if self._always_on_top else NSNormalWindowLevel
        for panel in (self._window, self._handle):
            if panel is not None:
                panel.setFloatingPanel_(self._always_on_top)
                panel.setLevel_(level)
                behavior = int(panel.collectionBehavior())
                behavior &= ~NSWindowCollectionBehaviorMoveToActiveSpace
                behavior |= NSWindowCollectionBehaviorCanJoinAllSpaces
                if self._always_on_top:
                    behavior |= NSWindowCollectionBehaviorFullScreenAuxiliary
                else:
                    behavior &= ~NSWindowCollectionBehaviorFullScreenAuxiliary
                panel.setCollectionBehavior_(behavior)

    def sync(self, settings):
        """Apply saved behavior without changing the user's visibility choice."""
        def work():
            self._auto_hide = settings.get("floatAutoHide", True) is not False
            was_on_top = self._always_on_top
            self._always_on_top = settings.get("floatAlwaysOnTop", True) is not False
            if self._window is None:
                return
            self._apply_window_policy()
            if was_on_top != self._always_on_top:
                for panel in (self._window, self._handle):
                    if panel is not None and panel.isVisible():
                        self._order_panel(panel)
                print(f"[seeUtoken] float always on top: {self._always_on_top}", flush=True)
            if not self._auto_hide:
                self._hide_at = None
                self._reveal()

        if sys.platform == "darwin":
            _run_on_main(work)

    def attach(self, pywindow):
        if sys.platform != "darwin":
            return

        def work():
            from AppKit import (
                NSWindowAnimationBehaviorNone,
            )
            from Foundation import NSTimer, NSRunLoop, NSRunLoopCommonModes
            from webview.platforms.cocoa import BrowserView

            browser = BrowserView.get_instance("pywebview_window", pywindow)
            if browser is None:
                return
            if self._window is browser.window and self._timer is not None:
                self._view = browser.webview
                self._push()
                return
            if self._timer is not None:
                self._timer.invalidate()
            self._window, was_visible = _use_overlay_panel(browser)
            self._view = browser.webview
            self._mouse_passthrough = None
            self._last_pointer = None
            self._set_mouse_passthrough(True)
            self._window.setAnimationBehavior_(NSWindowAnimationBehaviorNone)
            self._enabled = was_visible
            self._expanded = _rect(self._window.frame())
            self._create_handle()
            self._apply_window_policy()
            if was_visible:
                self._order_panel(self._window)
            self._target = _timer_target_class().alloc().init()
            self._target.controller = self
            self._timer = NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(
                0.04, self._target, "tick:", None, True
            )
            NSRunLoop.mainRunLoop().addTimer_forMode_(self._timer, NSRunLoopCommonModes)
            self._push()
            print(f"[seeUtoken] float edge dock: ready (always_on_top={self._always_on_top})", flush=True)

        _run_on_main(work)

    def _create_handle(self):
        from Quartz import CGColorCreateGenericRGB
        from AppKit import (
            NSPanel, NSView, NSColor, NSMakeRect, NSBackingStoreBuffered,
            NSWindowStyleMaskBorderless, NSWindowStyleMaskNonactivatingPanel,
            NSWindowAnimationBehaviorNone,
        )

        panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, 12, 56),
            NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel,
            NSBackingStoreBuffered, False,
        )
        panel.setTitle_("seeUtoken edge handle")
        panel.setReleasedWhenClosed_(False)
        panel.setOpaque_(False)
        panel.setBackgroundColor_(NSColor.clearColor())
        panel.setHasShadow_(False)
        panel.setHidesOnDeactivate_(False)
        panel.setAnimationBehavior_(NSWindowAnimationBehaviorNone)
        panel.setLevel_(self._window.level())
        panel.setCollectionBehavior_(self._window.collectionBehavior())
        view = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, 12, 56))
        view.setWantsLayer_(True)
        view.layer().setBackgroundColor_(CGColorCreateGenericRGB(.21, .24, .28, 1))
        view.layer().setCornerRadius_(5)
        view.layer().setMasksToBounds_(True)
        panel.setContentView_(view)
        self._handle = panel

    def set_visible(self, visible):
        def work():
            self._enabled = bool(visible)
            if self._handle is not None:
                if visible and self._collapsed:
                    self._order_panel(self._handle)
                    self._window.orderOut_(None)
                else:
                    self._handle.orderOut_(None)
                    if visible and self._window is not None:
                        self._order_panel(self._window)
        if sys.platform == "darwin":
            _run_on_main(work)

    def update_geometry(self, payload):
        if not isinstance(payload, dict) or not isinstance(payload.get("hitRects"), list):
            return

        def work():
            if self._window is None:
                return
            frame = _rect(self._window.frame())
            if abs(float(payload.get("width") or 0) - frame.width) > 1 or abs(float(payload.get("height") or 0) - frame.height) > 1:
                return  # stale report from before a collapse/expand
            self._geometry = payload
            self._input_path = None
            if payload.get("commands"):
                try:
                    self._input_path = _build_cg_path(payload["commands"], frame.height)
                except Exception:
                    pass  # Retain the reported hit rectangles on older systems.
            self._waiting_until = 0
            from AppKit import NSEvent
            point = NSEvent.mouseLocation()
            self._sync_mouse_input(frame, point.x, point.y, force_pointer=True)

        _run_on_main(work)

    def _rail(self, frame):
        raw = (self._geometry or {}).get("railRect")
        if isinstance(raw, dict):
            return Rect(frame.x + raw["x"], frame.top - raw["y"] - raw["height"], raw["width"], raw["height"])
        width, height = 66, min(214, frame.height)
        return Rect(frame.x if self._edge == "left" else frame.right - width,
                    frame.y + (frame.height - height) / 2, width, height)

    def _pointer_inside(self, frame, x, y):
        if self._collapsed:
            return frame.contains(x, y)
        if not frame.contains(x, y):
            return False
        for raw in (self._geometry or {}).get("hitRects", []):
            rect = Rect(frame.x + raw["x"], frame.top - raw["y"] - raw["height"], raw["width"], raw["height"])
            if rect.contains(x, y):
                return True
        return self._rail(frame).contains(x, y)

    def _set_mouse_passthrough(self, enabled):
        if self._window is not None and enabled != self._mouse_passthrough:
            self._window.setIgnoresMouseEvents_(enabled)
            self._mouse_passthrough = enabled

    def _sync_mouse_input(self, frame, x, y, force_pointer=False):
        """The invisible WebView reserve must not receive mouse clicks.

        Polling also forwards hover while AppKit ignores the window, so a
        stationary pointer can re-enter an icon without a click to activate it.
        Geometry and coordinates use logical points, including Retina screens.
        """
        inside = self._pointer_inside(frame, x, y)
        if self._input_path is not None:
            from Quartz import CGPathContainsPoint
            inside = bool(CGPathContainsPoint(self._input_path, None, (x - frame.x, y - frame.y), False))
        self._set_mouse_passthrough(not (inside or self._dragging))
        point = {"x": x - frame.x, "y": frame.top - y} if frame.contains(x, y) else None
        if self._view is not None and (force_pointer or point != self._last_pointer):
            self._last_pointer = point
            script = f"window.__seeUtokenFloatPointer?.({json.dumps(point)});"
            self._view.evaluateJavaScript_completionHandler_(script, None)

    def tick(self):
        from AppKit import NSEvent, NSScreen

        if self._window is None or not self._enabled:
            return
        if self._dragging:
            self._set_mouse_passthrough(False)
            return
        now = time.monotonic()
        if now < max(self._waiting_until, self._animating_until):
            self._set_mouse_passthrough(True)
            return
        if self._collapsed:
            self._set_mouse_passthrough(True)
            point = NSEvent.mouseLocation()
            if self._handle is not None and _rect(self._handle.frame()).contains(point.x, point.y):
                self._reveal()
            return
        if not self._window.isVisible():
            return
        frame = _rect(self._window.frame())
        point = NSEvent.mouseLocation()
        self._sync_mouse_input(frame, point.x, point.y)
        inside = self._pointer_inside(frame, point.x, point.y)
        if self._edge is None:
            screens = [_rect(screen.visibleFrame()) for screen in NSScreen.screens()]
            rail = self._rail(frame)
            edge, screen = edge_for(rail, screens)
            if edge:
                self._dock(frame, rail, edge, screen)
            return
        if not self._auto_hide:
            self._hide_at = None
            return
        if inside:
            self._hide_at = None
        elif self._hide_at is None:
            self._hide_at = now + self.HIDE_DELAY
        elif now >= self._hide_at:
            self._collapse()

    def _set_frame(self, frame):
        from AppKit import NSMakeRect

        self._geometry = None
        self._input_path = None
        self._set_mouse_passthrough(True)
        self._waiting_until = time.monotonic() + 0.04
        self._window.setFrame_display_(NSMakeRect(frame.x, frame.y, frame.width, frame.height), True)

    def _push(self):
        if self._view is None:
            return
        payload = json.dumps({"edge": self._edge, "collapsed": self._collapsed, "nativeHandle": True})
        script = f"window.__seeUtokenFloatDock={payload};window.__seeUtokenApplyFloatDock?.(window.__seeUtokenFloatDock);"
        self._view.evaluateJavaScript_completionHandler_(script, None)

    def _dock(self, frame, rail, edge, screen):
        self._edge, self._screen = edge, screen
        self._expanded = snapped_frame(frame, rail, edge, screen)
        self._rail_height = rail.height
        self._set_frame(self._expanded)
        self._hide_at = None
        self._push()
        self._save()

    def _collapse(self):
        if not self._auto_hide:
            return
        self._collapsed = True
        self._hide_at = None
        from AppKit import NSMakeRect

        tab = collapsed_frame(self._expanded, self._rail_height, self._edge, self._screen)
        self._handle.setFrame_display_(NSMakeRect(tab.x, tab.y, tab.width, tab.height), True)
        self._order_panel(self._handle)
        self._push()
        self._transition += 1
        transition = self._transition

        def finished():
            if self._collapsed and transition == self._transition:
                self._window.orderOut_(None)

        self._slide(self._offscreen_frame(), .14, finished)

    def _reveal(self):
        if not self._collapsed:
            return
        self._collapsed = False
        self._hide_at = None
        self._transition += 1
        if not self._enabled:
            self._set_frame(self._expanded)
            self._handle.orderOut_(None)
            self._push()
            return
        self._window.setFrameOrigin_((self._offscreen_frame().x, self._expanded.y))
        self._order_panel(self._window)
        self._push()
        self._handle.orderOut_(None)
        self._slide(self._expanded, .18)

    def _offscreen_frame(self):
        offset = -76 if self._edge == "left" else 76
        frame = self._expanded
        return Rect(frame.x + offset, frame.y, frame.width, frame.height)

    def _slide(self, frame, duration, completion=None):
        from AppKit import NSAnimationContext, NSMakeRect
        from Quartz import CAMediaTimingFunction

        self._animating_until = time.monotonic() + duration

        def animate(context):
            context.setDuration_(duration)
            context.setTimingFunction_(CAMediaTimingFunction.functionWithName_("easeOut"))
            self._window.animator().setFrame_display_(NSMakeRect(frame.x, frame.y, frame.width, frame.height), True)

        NSAnimationContext.runAnimationGroup_completionHandler_(animate, completion or (lambda: None))

    def reveal(self):
        if sys.platform == "darwin":
            _run_on_main(self._reveal)

    def set_dragging(self, dragging):
        if sys.platform != "darwin":
            return

        def work():
            if self._window is None:
                return
            if dragging:
                self._set_mouse_passthrough(False)
                self._reveal()
                if not self._dragging:
                    self._dragging, self._moved = True, False
                self._hide_at = None
                return
            if not self._dragging:
                return
            self._dragging = False
            from AppKit import NSEvent
            frame = _rect(self._window.frame())
            point = NSEvent.mouseLocation()
            self._sync_mouse_input(frame, point.x, point.y)
            if not self._moved:
                return
            from AppKit import NSScreen

            frame = _rect(self._window.frame())
            rail = self._rail(frame)
            edge, screen = edge_for(rail, [_rect(s.visibleFrame()) for s in NSScreen.screens()])
            if edge:
                self._dock(frame, rail, edge, screen)
            else:
                # A left-docked rail changes back to the usual right-aligned
                # layout. Preserve its screen position when changing layout.
                if self._edge == "left":
                    frame = Rect(rail.right - frame.width, frame.y, frame.width, frame.height)
                    self._set_frame(frame)
                self._edge = self._screen = None
                self._expanded = frame
                self._hide_at = None
                self._push()
                self._save()

        _run_on_main(work)

    def move_by(self, dx, dy):
        if sys.platform != "darwin":
            return False

        def work():
            if self._window is None:
                return
            self._reveal()
            if self._animating_until > time.monotonic():
                # A deliberate drag takes control immediately, without waiting
                # for an in-progress reveal animation.
                self._window.setFrameOrigin_((self._expanded.x, self._expanded.y))
                self._animating_until = 0
            self._dragging, self._moved = True, True
            frame = _rect(self._window.frame())
            self._window.setFrameOrigin_((frame.x + float(dx), frame.y - float(dy)))
            self._expanded = _rect(self._window.frame())

        _run_on_main(work)
        return self._window is not None

    def _save(self):
        if not self._persist or not self._expanded:
            return
        from AppKit import NSScreen

        frame = self._expanded
        primary = _rect(NSScreen.screens()[0].frame())
        position = (round(frame.x), round(primary.top - frame.top))
        if position != self._saved:
            self._saved = position
            threading.Thread(target=self._persist, args=position, daemon=True).start()

    def dispose(self):
        def work():
            if self._timer is not None:
                self._timer.invalidate()
            if self._target is not None:
                self._target.controller = None
            if self._handle is not None:
                self._handle.orderOut_(None)
                self._handle.close()
                self._handle = None
            self._window = self._view = self._timer = self._target = None
            self._input_path = None
            self._mouse_passthrough = self._last_pointer = None

        if sys.platform == "darwin":
            _run_on_main(work)
