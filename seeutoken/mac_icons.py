"""Native macOS app and status icons, keeping the original Retina bitmap."""

from __future__ import annotations

import sys
from pathlib import Path


def _image(path: Path, points: float, *, template: bool = False):
    from AppKit import NSImage

    image = NSImage.alloc().initWithContentsOfFile_(str(path.resolve()))
    if image is not None:
        # Change the logical size, retaining the full-resolution bitmap.
        image.setSize_((points, points))
        image.setTemplate_(template)
    return image


def set_application_icon(path: Path) -> bool:
    """Call on AppKit's main thread, including when running from source."""
    if sys.platform != "darwin" or not path.is_file():
        return False
    try:
        from AppKit import NSApplication

        image = _image(path, 512)
        if image is None:
            return False
        NSApplication.sharedApplication().setApplicationIconImage_(image)
        return True
    except Exception as exc:
        print(f"[seeUtoken] application icon: {exc}", flush=True)
        return False


def set_status_icon(icon, path: Path) -> bool:
    """Apply after pystray makes the item visible, on AppKit's main thread."""
    if sys.platform != "darwin" or not path.is_file():
        return False
    try:
        image = _image(path, 18, template=True)
        if image is None:
            return False
        # pystray's Cocoa backend first reduces images to menu-bar points,
        # losing Retina resolution. Replace that bitmap with the full source.
        button = icon._status_item.button()
        button.setImage_(image)
        button.setAccessibilityLabel_("seeUtoken 用量与额度")
        icon._icon_image = image
        return True
    except Exception as exc:
        print(f"[seeUtoken] status icon: {exc}", flush=True)
        return False
