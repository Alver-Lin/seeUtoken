"""Windows 11 desktop acrylic with an opaque fallback for older systems."""
from __future__ import annotations

import ctypes
import sys

from .storage import is_light_appearance, is_liquid_glass_style


class _Margins(ctypes.Structure):
    _fields_ = [(name, ctypes.c_int) for name in ('left', 'right', 'top', 'bottom')]


def transparency_enabled():
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize') as key:
            return bool(winreg.QueryValueEx(key, 'EnableTransparency')[0])
    except OSError:
        return True


def apply_material(form, mode, *, shaped=False):
    """Use desktop acrylic for framed windows, layered alpha for shaped windows."""
    from System.Drawing import Color

    reduced = not transparency_enabled()
    wants_glass = is_liquid_glass_style(mode) and not reduced
    glass = wants_glass and not shaped and sys.getwindowsversion().build >= 22621
    state = {'platform': 'win32', 'type': 'opaque', 'reducedTransparency': reduced,
             'fallbackReason': None, 'floatStyle': mode}
    config = (mode, reduced, glass, shaped)
    if getattr(form, '_seeutoken_material_config', None) == config:
        return dict(form._seeutoken_material_state)

    handle = ctypes.c_void_p(form.Handle.ToInt64())
    dwm = ctypes.windll.dwmapi
    # DWMSBT_TRANSIENTWINDOW uses Desktop Acrylic. CSS supplies separate standard
    # and clear tint densities instead of fading the entire window and its text.
    kind = ctypes.c_int(3 if glass else 1)
    result = dwm.DwmSetWindowAttribute(handle, 38, ctypes.byref(kind), ctypes.sizeof(kind))
    margins = _Margins(*([-1] * 4 if glass and result == 0 else [0] * 4))
    extended = dwm.DwmExtendFrameIntoClientArea(handle, ctypes.byref(margins))
    glass = glass and result == 0 and extended == 0
    dark = ctypes.c_int(not is_light_appearance(mode))
    dwm.DwmSetWindowAttribute(handle, 20, ctypes.byref(dark), ctypes.sizeof(dark))
    # DWM acrylic ignores a WinForms Region when painting its backdrop. A layered
    # shaped window retains both visual clipping and click-through outside it.
    form.Opacity = .80 if shaped and wants_glass and mode.endswith('-clear') else 1.0
    if glass:
        form.BackColor = Color.Black
        form.webview.DefaultBackgroundColor = Color.Transparent
        state['type'] = 'windows-acrylic'
    else:
        color = Color.FromArgb(245, 247, 249) if is_light_appearance(mode) else Color.FromArgb(17, 24, 36)
        form.BackColor = color
        form.webview.DefaultBackgroundColor = color
        if shaped and wants_glass:
            state['type'] = 'windows-translucent'
        elif wants_glass:
            state['fallbackReason'] = 'Desktop acrylic unavailable'
    form._seeutoken_material_config = config
    form._seeutoken_material_state = dict(state)
    return state


def sync_material(window, mode):
    from System import Action

    form = getattr(window, 'native', None)
    if form is None:
        return {'platform': 'win32', 'type': 'opaque', 'floatStyle': mode}
    state = {}

    def update():
        state.update(apply_material(form, mode))

    if form.InvokeRequired:
        form.Invoke(Action(update))
    else:
        update()
    return state
