"""Track float-window hover even when another application has focus."""

from __future__ import annotations

import json
import sys
from typing import Any

from .float_native_material import _run_on_main

_owner_class = None


def _tracking_owner_class():
    global _owner_class
    if _owner_class is None:
        from Foundation import NSObject

        class SeeUtokenFloatTrackingOwner(NSObject):
            def mouseEntered_(self, event):
                self.controller.send_point(event)

            def mouseMoved_(self, event):
                self.controller.send_point(event)

            def mouseExited_(self, event):
                self.controller.send_point(None)

        _owner_class = SeeUtokenFloatTrackingOwner
    return _owner_class


class FloatPointerController:
    def __init__(self) -> None:
        self._webview: Any = None
        self._owner: Any = None
        self._area: Any = None
        self._last_point: Any = None

    def attach(self, window: Any) -> None:
        if sys.platform != "darwin":
            return

        def work():
            from AppKit import (
                NSTrackingActiveAlways,
                NSTrackingArea,
                NSTrackingInVisibleRect,
                NSTrackingMouseEnteredAndExited,
                NSTrackingMouseMoved,
            )
            from webview.platforms.cocoa import BrowserView

            self._detach()
            browser = BrowserView.get_instance("pywebview_window", window)
            if browser is None:
                return
            view = browser.webview
            owner = _tracking_owner_class().alloc().init()
            owner.controller = self
            options = (
                NSTrackingActiveAlways
                | NSTrackingInVisibleRect
                | NSTrackingMouseEnteredAndExited
                | NSTrackingMouseMoved
            )
            area = NSTrackingArea.alloc().initWithRect_options_owner_userInfo_(
                view.bounds(), options, owner, None
            )
            self._webview, self._owner, self._area = view, owner, area
            browser.window.setAcceptsMouseMovedEvents_(True)
            view.addTrackingArea_(area)
            print("[seeUtoken] float hover tracking: active always", flush=True)

        _run_on_main(work)

    def send_point(self, event: Any) -> None:
        """AppKit points and CSS pixels share logical units (including Retina)."""
        view = self._webview
        if view is None:
            return
        point = None
        if event is not None:
            location = view.convertPoint_fromView_(event.locationInWindow(), None)
            bounds = view.bounds()
            x = float(location.x - bounds.origin.x)
            y = float(location.y - bounds.origin.y)
            if not view.isFlipped():
                y = float(bounds.size.height) - y
            point = {"x": x, "y": y}
        if point == self._last_point:
            return
        self._last_point = point
        # Do not call pywebview.evaluate_js on the AppKit thread: it blocks.
        script = f"window.__seeUtokenFloatPointer?.({json.dumps(point)});"
        view.evaluateJavaScript_completionHandler_(script, None)

    def _detach(self) -> None:
        if self._webview is not None and self._area is not None:
            self._webview.removeTrackingArea_(self._area)
        if self._owner is not None:
            self._owner.controller = None
        self._webview = self._owner = self._area = None
        self._last_point = None

    def dispose(self) -> None:
        if sys.platform == "darwin":
            _run_on_main(self._detach)
