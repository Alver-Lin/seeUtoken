"""Framed main-window appearance, independent of the float window's shaped material."""
from __future__ import annotations

import sys

from .float_native_material import (
    FloatNativeMaterialController,
    _fix_webview_transparency,
    _ns_window_for,
    _reduce_transparency,
    _run_on_main,
    _style_from_settings,
)
from .mac_liquid_glass import MacLiquidGlass, liquid_glass_supported
from .storage import is_light_appearance, is_liquid_glass_style, normalize_float_glass_style


def _configure_window(ns, mode: str, transparent: bool) -> None:
    from AppKit import NSAppearance, NSColor

    dark = not is_light_appearance(mode)
    ns.setAppearance_(NSAppearance.appearanceNamed_("NSAppearanceNameDarkAqua" if dark else "NSAppearanceNameAqua"))
    ns.setOpaque_(not transparent)
    ns.setHasShadow_(True)
    ns.setTitlebarAppearsTransparent_(transparent)
    if transparent:
        background = NSColor.clearColor()
    else:
        red, green, blue = (17, 24, 36) if dark else (245, 247, 249)
        background = NSColor.colorWithSRGBRed_green_blue_alpha_(red / 255, green / 255, blue / 255, 1)
    ns.setBackgroundColor_(background)
    # pywebview pins a separate titlebar background when constructing a framed window.
    # AppKit clips content materials below the titlebar. Give the native titlebar
    # its own translucent backing so Clear never leaves the title over raw wallpaper.
    from AppKit import NSWindowCloseButton

    button = ns.standardWindowButton_(NSWindowCloseButton)
    titlebar = button.superview() if button else None
    container = titlebar.superview() if titlebar else None
    if container:
        from AppKit import (
            NSVisualEffectView, NSVisualEffectBlendingModeBehindWindow,
            NSVisualEffectMaterialHUDWindow, NSVisualEffectStateActive,
            NSViewWidthSizable, NSViewHeightSizable, NSWindowBelow,
        )

        # A dedicated child is necessary: AppKit repaints the container's own
        # backing layer, discarding a backgroundColor set directly on that layer.
        material_id = "seeutoken-titlebar-material"
        material = next((view for view in container.subviews()
                         if view.identifier() == material_id), None)
        if transparent:
            if material is None:
                material = NSVisualEffectView.alloc().initWithFrame_(container.bounds())
                material.setIdentifier_(material_id)
                material.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
                material.setBlendingMode_(NSVisualEffectBlendingModeBehindWindow)
                material.setMaterial_(NSVisualEffectMaterialHUDWindow)
                material.setState_(NSVisualEffectStateActive)
                container.addSubview_positioned_relativeTo_(material, NSWindowBelow, titlebar)
            material.setAppearance_(ns.appearance())
            material.setAlphaValue_(.85 if mode.endswith("-clear") else 1)
            material.setHidden_(False)
        elif material is not None:
            material.setHidden_(True)
        if container.respondsToSelector_("setBackgroundColor:"):
            container.setBackgroundColor_(background)
    if titlebar:
        for view in titlebar.subviews():
            if view.respondsToSelector_("setTextColor:"):
                # Inactive native titles otherwise become hard to read on Clear.
                view.setTextColor_(NSColor.colorWithSRGBRed_green_blue_alpha_(.94, .96, .99, 1) if dark else NSColor.windowFrameTextColor())


class MainNativeMaterialController(FloatNativeMaterialController):
    """Reuse safe WebView delivery and material cleanup, without float geometry."""

    def sync(self, settings: dict | None = None, on_complete=None) -> dict:
        settings = settings or {}
        mode = normalize_float_glass_style(settings.get("floatGlassStyle"))
        if sys.platform != "darwin":
            self._state = {**self._state, "floatStyle": mode, "type": "opaque"}
            if on_complete:
                on_complete()
            return self.get_state()

        def work():
            ns = _ns_window_for(self._win)
            if ns is None:
                return
            reduced = _reduce_transparency()
            supported = liquid_glass_supported()
            config = (ns, mode, reduced, supported)
            if self._material_config != config:
                self._dispose_glass()
                self._dispose_vibrancy()
                failure = None
                kind = "opaque"
                wants_glass = is_liquid_glass_style(mode) and not reduced
                _fix_webview_transparency(ns)
                if wants_glass:
                    if supported:
                        try:
                            self._glass = MacLiquidGlass(ns)
                            style, tint = _style_from_settings(settings)
                            self._glass.update(dark=not is_light_appearance(mode), radius=0, style=style, tint_opacity=tint)
                            kind = "liquid-glass"
                        except Exception as exc:
                            failure = str(exc)
                            self._dispose_glass()
                    if self._glass is None:
                        try:
                            self._ensure_vibrancy(ns)
                            kind = "vibrancy"
                        except Exception as exc:
                            failure = str(exc)
                            self._dispose_vibrancy()
                _configure_window(ns, mode, kind != "opaque")
                self._state = {
                    "floatStyle": mode,
                    "type": kind,
                    "reducedTransparency": reduced,
                    "highContrast": False,
                    "fallbackReason": failure,
                    "liquidGlassSupported": supported,
                }
                self._material_config = config
            if on_complete:
                on_complete()

        _run_on_main(work)
        return self.get_state()
