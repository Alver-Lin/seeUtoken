"""本地设置持久化。"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DEFAULT_PANELS = [
    {"id": "cursor-default", "type": "cursor", "name": "Cursor", "createdAt": 0},
    {"id": "codex-default", "type": "codex", "name": "Codex", "createdAt": 0},
    {"id": "qoder-default", "type": "qoder", "name": "Qoder", "createdAt": 0},
]

DEFAULT_SETTINGS: dict[str, Any] = {
    "manualToken": "",
    "autoRefreshMinutes": 5,
    "codexAutoRefreshMinutes": 1,
    "includeCachedTokens": False,
    "showFloat": True,
    "floatAutoHide": True,
    "floatAlwaysOnTop": True,
    "floatCollapsed": False,
    "useDemoWhenLoggedOut": False,
    "floatX": None,
    "floatY": None,
    "panels": list(DEFAULT_PANELS),
    # light | dark | liquid | liquid-clear | liquid-light | liquid-light-clear
    "floatGlassStyle": "light",
}

FLOAT_GLASS_STYLES = ("light", "dark", "liquid", "liquid-clear", "liquid-light", "liquid-light-clear")


def is_light_appearance(mode: str) -> bool:
    return mode in ("light", "liquid-light", "liquid-light-clear")


def is_liquid_glass_style(mode: str) -> bool:
    return mode in FLOAT_GLASS_STYLES and mode.startswith("liquid")


def normalize_float_glass_style(value: Any) -> str:
    mode = str(value or "").strip()
    return mode if mode in FLOAT_GLASS_STYLES else DEFAULT_SETTINGS["floatGlassStyle"]


def normalize_panels(value: Any) -> list[dict[str, Any]]:
    """One panel per provider, preserving the first panel's metadata and order."""
    source = value if isinstance(value, list) else DEFAULT_PANELS
    panels = []
    seen = set()
    for panel in source:
        if not isinstance(panel, dict):
            continue
        provider = str(panel.get("type") or panel.get("provider") or "cursor").strip().lower()
        if not provider or provider in seen:
            continue
        seen.add(provider)
        panels.append({**panel, "type": provider})
    return panels


def settings_path() -> Path:
    if os.name == "nt":
        root = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        root = Path.home() / ".config"
    return root / "seeUtoken" / "settings.json"


def usage_cache_path() -> Path:
    return settings_path().parent / "usage_cache.json"


def load_usage_cache() -> dict[str, Any] | None:
    path = usage_cache_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict) and isinstance(raw.get("data"), dict):
            return raw
    except Exception:
        pass
    return None


def save_usage_cache(payload: dict[str, Any]) -> None:
    if not payload or not isinstance(payload.get("data"), dict):
        return
    if payload["data"].get("demo"):
        return
    try:
        path = usage_cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        # 热力图体积大，磁盘缓存不存，避免拖慢读写
        data = {k: v for k, v in payload["data"].items() if k != "heatmap"}
        slim = {**payload, "data": data}
        path.write_text(json.dumps(slim, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


class SettingsStore:
    def __init__(self) -> None:
        self.path = settings_path()
        self.data = self.load()

    def load(self) -> dict[str, Any]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            merged = {**DEFAULT_SETTINGS, **raw}
            merged["floatGlassStyle"] = normalize_float_glass_style(merged.get("floatGlassStyle"))
            merged["panels"] = normalize_panels(merged.get("panels"))
            return merged
        except Exception:
            return {**DEFAULT_SETTINGS, "panels": list(DEFAULT_PANELS)}

    def save(self, partial: dict[str, Any] | None = None) -> dict[str, Any]:
        if partial:
            self.data.update(partial)
        self.data["floatGlassStyle"] = normalize_float_glass_style(self.data.get("floatGlassStyle"))
        self.data["panels"] = normalize_panels(self.data.get("panels"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        return self.data

    def get(self) -> dict[str, Any]:
        return self.data
