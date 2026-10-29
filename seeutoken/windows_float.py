"""Clip the Windows sidebar to its DOM outline instead of a 400px rectangle."""
from __future__ import annotations

import logging

from .storage import is_light_appearance


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

    def update():
        from System.Drawing import Color, PointF, Region
        from System.Drawing.Drawing2D import FillMode, GraphicsPath, Matrix

        try:
            color = Color.FromArgb(248, 251, 255) if is_light_appearance(mode) else Color.FromArgb(48, 52, 56)
            form.BackColor = color
            form.webview.DefaultBackgroundColor = color
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
            finally:
                matrix.Dispose()
                path.Dispose()
        except Exception:
            logging.exception('Unable to update Windows sidebar outline')

    if form.InvokeRequired:
        form.Invoke(Action(update))
    else:
        update()
