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
    "showFloat": True,
    "floatCollapsed": True,
    "useDemoWhenLoggedOut": True,
    "floatX": None,
    "floatY": None,
    "panels": list(DEFAULT_PANELS),
}


def settings_path() -> Path:
    if os.name == "nt":
        root = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        root = Path.home() / ".config"
    return root / "seeUtoken" / "settings.json"


class SettingsStore:
    def __init__(self) -> None:
        self.path = settings_path()
        self.data = self.load()

    def load(self) -> dict[str, Any]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            merged = {**DEFAULT_SETTINGS, **raw}
            if not isinstance(merged.get("panels"), list) or not merged["panels"]:
                merged["panels"] = list(DEFAULT_PANELS)
            return merged
        except Exception:
            return {**DEFAULT_SETTINGS, "panels": list(DEFAULT_PANELS)}

    def save(self, partial: dict[str, Any] | None = None) -> dict[str, Any]:
        if partial:
            self.data.update(partial)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        return self.data

    def get(self) -> dict[str, Any]:
        return self.data
