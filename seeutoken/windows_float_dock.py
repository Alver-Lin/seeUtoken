"""Windows edge docking in physical screen pixels, without resizing WebView2."""
from __future__ import annotations

import ctypes
import json
import logging
import threading
import time

from .float_dock import Rect, edge_for, snapped_frame


def _rect(bounds):
    return Rect(float(bounds.X), float(bounds.Y), float(bounds.Width), float(bounds.Height))


def handle_frame(frame, rail_height, edge, screen, scale=1):
    width = min(12 * scale, screen.width)
    height = min(56 * scale, rail_height, screen.height)
    y = min(max(frame.y + (frame.height - height) / 2, screen.y), screen.top - height)
    return Rect(screen.x if edge == 'left' else screen.right - width, y, width, height)


class _WinFormsHost:
    """All methods except invoke run on the existing WinForms UI thread."""
    def __init__(self, window):
        from ctypes import wintypes

        self.window, self.form = window, window.native
        self.handle = self.timer = None
        self.user = ctypes.WinDLL('user32', use_last_error=True)
        self.user.SetWindowPos.argtypes = (wintypes.HWND, wintypes.HWND, ctypes.c_int,
                                          ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT)
        self.user.SetWindowPos.restype = wintypes.BOOL
        self.user.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
        self.user.ShowWindow.restype = wintypes.BOOL
        self.user.IsWindowVisible.argtypes = (wintypes.HWND,)
        self.user.IsWindowVisible.restype = wintypes.BOOL

    def invoke(self, work):
        from System import Action

        if self.form.IsDisposed:
            return None
        if not self.form.InvokeRequired:
            return work()
        result = []
        self.form.Invoke(Action(lambda: result.append(work())))
        return result[0] if result else None

    def start(self, tick):
        from System.Drawing import Color, Size
        from System.Windows.Forms import AutoScaleMode, Form, FormBorderStyle, FormStartPosition, Timer

        self.handle = Form()
        self.handle.Text = 'seeUtoken edge handle'
        self.handle.FormBorderStyle = getattr(FormBorderStyle, 'None')
        self.handle.ShowInTaskbar = False
        self.handle.StartPosition = FormStartPosition.Manual
        self.handle.AutoScaleMode = getattr(AutoScaleMode, 'None')
        self.handle.ClientSize = Size(12, 56)
        self.handle.BackColor = Color.FromArgb(54, 61, 71)
        # Create the native handle without Show(), which would activate the app.
        _ = self.handle.Handle
        self._tick = lambda *_: tick()
        self.timer = Timer()
        self.timer.Interval = 40
        self.timer.Tick += self._tick
        self.timer.Start()

    @property
    def scale(self):
        return max(.5, float(getattr(self.form, '_scale', 1) or 1))

    @property
    def frame(self):
        return _rect(self.form.Bounds)

    @property
    def client_size(self):
        return float(self.form.ClientSize.Width), float(self.form.ClientSize.Height)

    @property
    def client_origin(self):
        from System.Drawing import Point

        point = self.form.PointToScreen(Point(0, 0))
        return float(point.X), float(point.Y)

    def screens(self):
        from System.Windows.Forms import Screen

        return [_rect(screen.WorkingArea) for screen in Screen.AllScreens]

    def pointer(self):
        from System.Windows.Forms import Cursor

        point = Cursor.Position
        return float(point.X), float(point.Y)

    def visible(self, handle=False):
        form = self.handle if handle else self.form
        return bool(form is not None and not form.IsDisposed and self.user.IsWindowVisible(form.Handle.ToInt64()))

    def move(self, frame, handle=False):
        form = self.handle if handle else self.form
        # NOZORDER | NOACTIVATE: moving the dock must not steal keyboard focus.
        if not self.user.SetWindowPos(form.Handle.ToInt64(), None, round(frame.x), round(frame.y),
                                      round(frame.width), round(frame.height), 0x14):
            raise ctypes.WinError(ctypes.get_last_error())

    def show(self, visible, handle=False):
        form = self.handle if handle else self.form
        if self.visible(handle) != bool(visible):
            self.user.ShowWindow(form.Handle.ToInt64(), 4 if visible else 0)

    def topmost(self, enabled):
        for form in (self.form, self.handle):
            if not self.user.SetWindowPos(form.Handle.ToInt64(), -1 if enabled else -2,
                                         0, 0, 0, 0, 0x13):
                raise ctypes.WinError(ctypes.get_last_error())

    def script(self, script):
        # evaluate_js waits on WebView2; it must never run on this UI thread.
        self.form.webview.ExecuteScriptAsync(script)

    def dispose(self):
        if self.timer is not None:
            self.timer.Stop()
            self.timer.Dispose()
            self.timer = None
        if self.handle is not None:
            self.handle.Close()
            self.handle.Dispose()
            self.handle = None


class WindowsFloatDockController:
    HIDE_DELAY = .65

    def __init__(self, persist=None, settings=None):
        self._host = None
        self._persist = persist
        self._auto_hide = (settings or {}).get('floatAutoHide', True) is not False
        self._always_on_top = (settings or {}).get('floatAlwaysOnTop', True) is not False
        self._enabled = False
        self._collapsed = False
        self._dragging = self._moved = False
        self._edge = self._screen = self._expanded = None
        self._geometry = None
        self._hide_at = None
        self._waiting_until = 0
        self._rail_height = 214
        self._saved = None

    @property
    def attached(self):
        return self._host is not None

    def _dispatch(self, work):
        return self._host.invoke(work) if self._host is not None else None

    def attach(self, window):
        if self._host is not None:
            self._dispatch(self._push)
            return
        if getattr(window, 'native', None) is None:
            return
        host = _WinFormsHost(window)
        self._host = host

        def setup():
            self._enabled = host.visible()
            self._expanded = host.frame
            host.start(self._safe_tick)
            host.topmost(self._always_on_top)
            self._push()
        try:
            host.invoke(setup)
        except Exception:
            logging.exception('Unable to initialize Windows edge dock; retaining the regular sidebar')
            try:
                host.invoke(host.dispose)
            finally:
                self._host = None
                self._enabled = False

    def _safe_tick(self):
        try:
            self.tick()
        except Exception:
            logging.exception('Unable to update Windows edge dock')

    def sync(self, settings):
        self._auto_hide = settings.get('floatAutoHide', True) is not False
        self._always_on_top = settings.get('floatAlwaysOnTop', True) is not False

        def work():
            self._host.topmost(self._always_on_top)
            if not self._auto_hide:
                self._hide_at = None
                self._reveal()
        self._dispatch(work)

    def set_visible(self, visible):
        def work():
            self._enabled = bool(visible)
            self._hide_at = None
            self._host.show(visible and not self._collapsed)
            self._host.show(visible and self._collapsed, handle=True)
        self._dispatch(work)

    def update_geometry(self, payload):
        if not isinstance(payload, dict) or not isinstance(payload.get('hitRects'), list):
            return

        def work():
            width, height = self._host.client_size
            scale = self._host.scale
            if abs(float(payload.get('width') or 0) * scale - width) > 2 or abs(float(payload.get('height') or 0) * scale - height) > 2:
                return
            self._geometry = payload
            self._waiting_until = 0
            self._rail_height = self._rail().height
        self._dispatch(work)

    def _css_rect(self, rect):
        width, height = self._host.client_size
        geometry = self._geometry or {}
        sx = width / float(geometry.get('width') or width / self._host.scale)
        sy = height / float(geometry.get('height') or height / self._host.scale)
        x, y = self._host.client_origin
        return Rect(x + float(rect['x']) * sx, y + float(rect['y']) * sy,
                    float(rect['width']) * sx, float(rect['height']) * sy)

    def _rail(self):
        raw = (self._geometry or {}).get('railRect')
        if isinstance(raw, dict):
            return self._css_rect(raw)
        frame, scale = self._host.frame, self._host.scale
        width, height = 66 * scale, min(214 * scale, frame.height)
        return Rect(frame.x if self._edge == 'left' else frame.right - width,
                    frame.y + (frame.height - height) / 2, width, height)

    def _inside(self, x, y):
        if not self._host.frame.contains(x, y):
            return False
        return self._rail().contains(x, y) or any(
            self._css_rect(rect).contains(x, y) for rect in (self._geometry or {}).get('hitRects', []))

    def tick(self):
        if self._host is None or not self._enabled or self._dragging:
            return
        now = time.monotonic()
        if now < self._waiting_until:
            return
        screens = self._host.screens()
        if not screens:
            return
        if self._screen is not None and self._screen not in screens:
            # A monitor was removed or its taskbar/work area changed.
            self._reveal()
            frame = self._host.frame
            screen = min(screens, key=lambda s: abs(s.x - frame.x) + abs(s.y - frame.y))
            self._edge = self._screen = None
            self._set_frame(Rect(min(max(frame.x, screen.x), max(screen.x, screen.right - frame.width)),
                                 min(max(frame.y, screen.y), max(screen.y, screen.top - frame.height)), frame.width, frame.height))
            self._push()
            self._save()
            return
        x, y = self._host.pointer()
        if self._collapsed:
            tab = handle_frame(self._expanded, self._rail_height, self._edge, self._screen, self._host.scale)
            if tab.contains(x, y):
                self._reveal()
            return
        if not self._host.visible():
            return
        if self._edge is None:
            edge, screen = edge_for(self._rail(), screens, 16 * self._host.scale)
            if edge:
                self._dock(edge, screen)
            return
        if not self._auto_hide or self._inside(x, y):
            self._hide_at = None
        elif self._hide_at is None:
            self._hide_at = now + self.HIDE_DELAY
        elif now >= self._hide_at:
            self._collapse()

    def _set_frame(self, frame):
        self._geometry = None
        self._waiting_until = time.monotonic() + .12
        self._host.move(frame)
        self._expanded = self._host.frame

    def _push(self):
        state = json.dumps({'edge': self._edge, 'collapsed': self._collapsed, 'nativeHandle': True})
        self._host.script(f'window.__seeUtokenFloatDock={state};window.__seeUtokenApplyFloatDock?.(window.__seeUtokenFloatDock);')

    def _dock(self, edge, screen):
        rail = self._rail()
        geometry = self._geometry if (self._edge == 'left') == (edge == 'left') else None
        self._edge, self._screen = edge, screen
        self._rail_height = rail.height
        self._set_frame(snapped_frame(self._host.frame, rail, edge, screen))
        self._geometry = geometry
        self._hide_at = None
        self._push()
        self._save()

    def _collapse(self):
        if not self._auto_hide or self._dragging or self._edge is None:
            return
        self._expanded = self._host.frame
        self._collapsed = True
        self._hide_at = None
        tab = handle_frame(self._expanded, self._rail_height, self._edge, self._screen, self._host.scale)
        self._host.move(tab, handle=True)
        self._push()
        self._host.show(True, handle=True)
        self._host.show(False)

    def _reveal(self):
        if not self._collapsed:
            return
        self._collapsed = False
        self._hide_at = None
        self._host.show(False, handle=True)
        self._host.show(self._enabled)
        self._push()

    def reveal(self):
        self._dispatch(self._reveal)

    def set_dragging(self, dragging):
        def work():
            if dragging:
                self._reveal()
                if not self._dragging:
                    self._dragging, self._moved = True, False
                self._hide_at = None
                return
            if not self._dragging:
                return
            self._dragging = False
            if not self._moved:
                return
            rail, frame = self._rail(), self._host.frame
            edge, screen = edge_for(rail, self._host.screens(), 16 * self._host.scale)
            if edge:
                self._dock(edge, screen)
            else:
                if self._edge == 'left':
                    self._set_frame(Rect(rail.right - frame.width, frame.y, frame.width, frame.height))
                self._edge = self._screen = None
                self._hide_at = None
                self._push()
                self._save()
        self._dispatch(work)

    def move_by(self, dx, dy):
        def work():
            self._reveal()
            self._dragging = self._moved = True
            frame, scale = self._host.frame, self._host.scale
            self._host.move(Rect(frame.x + float(dx) * scale, frame.y + float(dy) * scale, frame.width, frame.height))
            self._expanded = self._host.frame
        if self._host is None:
            return False
        self._dispatch(work)
        return True

    def _save(self):
        if self._persist is None or self._expanded is None:
            return
        scale = self._host.scale
        position = (round(self._expanded.x / scale), round(self._expanded.y / scale))
        if position != self._saved:
            self._saved = position
            threading.Thread(target=self._persist, args=position, daemon=True).start()

    def dispose(self):
        def work():
            self._enabled = False
            self._host.dispose()
        self._dispatch(work)
        self._host = None
