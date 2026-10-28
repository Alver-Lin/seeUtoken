"""Read bundled assets without modifying the signed macOS application."""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path


def resource_root() -> Path:
    return Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent


def prepare_ui(root: Path, *, frozen: bool | None = None):
    source = root / "ui"
    if frozen is None:
        frozen = bool(getattr(sys, "frozen", False))
    if not frozen:
        return source, None
    # Bootstrap HTML includes the current user's statistics. Keep these writes
    # outside .app, which may be read-only and must retain its code signature.
    temporary = tempfile.TemporaryDirectory(prefix="seeutoken-ui-")
    destination = Path(temporary.name) / "ui"
    try:
        shutil.copytree(source, destination)
    except Exception:
        temporary.cleanup()
        raise
    return destination, temporary
