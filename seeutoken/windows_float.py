"""Clip the Windows sidebar to its DOM outline instead of a 400px rectangle."""
from __future__ import annotations

import logging
import ctypes

WS_EX_TOOLWINDOW = 0x80
WS_EX_APPWINDOW = 0x40000


def _window_style(form, hide=False):
    from ctypes import wintypes

    user = ctypes.WinDLL('user32', use_last_error=True)
    user.GetWindowLongPtrW.argtypes = (wintypes.HWND, ctypes.c_int)
    user.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    handle = form.Handle.ToInt64()
    style = user.GetWindowLongPtrW(handle, -20)
    if hide:
        desired = (style | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW
        if desired != style:
            user.SetWindowLongPtrW.argtypes = (wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t)
            user.SetWindowLongPtrW.restype = ctypes.c_ssize_t
            ctypes.set_last_error(0)
            previous = user.SetWindowLongPtrW(handle, -20, desired)
            if not previous and ctypes.get_last_error():
                raise ctypes.WinError(ctypes.get_last_error())
            user.SetWindowPos.argtypes = (wintypes.HWND, wintypes.HWND, ctypes.c_int,
                                         ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT)
            # Refresh the frame without moving, resizing, raising or activating it.
            if not user.SetWindowPos(handle, None, 0, 0, 0, 0, 0x37):
                raise ctypes.WinError(ctypes.get_last_error())
        return desired
    return style


def taskbar_hidden(window):
    form = getattr(window, 'native', None)
    if form is None:
        return False
    style = _window_style(form)
    return bool(style & WS_EX_TOOLWINDOW) and not bool(style & WS_EX_APPWINDOW)

def hide_from_taskbar(window):
    """Configure the float before its first Show; keep the main window independent."""
    form = getattr(window, 'native', None)
    if form is None:
        return
    from System import Action

    def update():
        # ShowInTaskbar's WinForms setter recreates the HWND and can abort an
        # in-flight WebView2 initialization. Change shell styles in place instead.
        def apply_style(*_):
            if form.IsHandleCreated and not form.IsDisposed:
                _window_style(form, hide=True)

        if getattr(form, '_seeutoken_taskbar_handler', None) is None:
            form._seeutoken_taskbar_handler = apply_style
            form.HandleCreated += apply_style
            form.StyleChanged += apply_style
        apply_style()

    if form.InvokeRequired:
        form.Invoke(Action(update))
    else:
        update()


def set_topmost(window, enabled):
    """WinForms TopMost must be changed on its owning UI thread."""
    form = getattr(window, 'native', None)
    if form is None:
        return
    from System import Action

    def update():
        window.on_top = bool(enabled)
        handler = getattr(form, '_seeutoken_taskbar_handler', None)
        if handler:
            handler()

    if form.InvokeRequired:
        form.BeginInvoke(Action(update))
    else:
        update()


def build_path(commands, path, point):
    """Convert the shared CSS-coordinate outline to a System.Drawing path."""
    current = None
    for command in commands:
        op, *coords = command
        if op == 'M':
            path.StartFigure()
            current = point(float(coords[0]), float(coords[1]))
        elif op == 'L' and current is not None:
            end = point(float(coords[0]), float(coords[1]))
            path.AddLine(current, end)
            current = end
        elif op == 'C' and current is not None:
            points = [point(float(coords[i]), float(coords[i + 1])) for i in (0, 2, 4)]
            path.AddBezier(current, *points)
            current = points[-1]
        elif op == 'Z':
            path.CloseFigure()
    return path


def apply_sidebar(window, mode, shape=None):
    """Run on the WinForms thread; Region removes unused pixels and mouse hits."""
    form = getattr(window, 'native', None)
    if form is None:
        return
    from System import Action

    state = {}

    def update():
        from System.Drawing import PointF, Region
        from System.Drawing.Drawing2D import FillMode, GraphicsPath, Matrix

        try:
            from .windows_material import apply_material

            state.update(apply_material(form, mode, shaped=True))
            # WinForms Opacity/TopMost updates can restore WS_EX_APPWINDOW from
            # CreateParams. Reapply after the material change on the same UI turn.
            handler = getattr(form, '_seeutoken_taskbar_handler', None)
            if handler:
                handler()
            if not shape or not shape.get('commands'):
                return
            width, height = float(shape.get('width') or 0), float(shape.get('height') or 0)
            if width <= 0 or height <= 0:
                return
            path = GraphicsPath(FillMode.Winding)
            matrix = Matrix()
            try:
                build_path(shape['commands'], path, PointF)
                # The DOM uses CSS pixels; WinForms ClientSize follows monitor DPI.
                matrix.Scale(float(form.ClientSize.Width) / width, float(form.ClientSize.Height) / height)
                path.Transform(matrix)
                previous = form.Region
                form.Region = Region(path)
                if previous is not None:
                    previous.Dispose()
                # Layered windows otherwise retain pixels from the previous
                # provider until an unrelated mouse/paint event invalidates them.
                form.Refresh()
            finally:
                matrix.Dispose()
                path.Dispose()
        except Exception:
            logging.exception('Unable to update Windows sidebar outline')

    if form.InvokeRequired:
        form.Invoke(Action(update))
    else:
        update()
    return state
