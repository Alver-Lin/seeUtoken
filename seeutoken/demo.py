"""未登录时的演示数据。"""

from __future__ import annotations

import time
from typing import Any

from .heatmap import get_demo_heatmap


def get_demo_data() -> dict[str, Any]:
    now = int(time.time() * 1000)
    cycle_start = now - 13 * 86_400_000
    cycle_end = now + 13 * 86_400_000
    year = time.localtime().tm_year

    cycle_models = [
        {
            "model": "auto",
            "cost": 349.83,
            "percent": 97,
            "calls": 700,
            "input": 22_000_000,
            "output": 3_100_000,
            "cache": 575_000_000,
        },
        {
            "model": "grok-4.7-high-fast",
            "cost": 5.85,
            "percent": 1.6,
            "calls": 1,
            "input": 120_000,
            "output": 28_000,
            "cache": 5_100_000,
        },
        {
            "model": "cursor-grok-4.6-high-fast",
            "cost": 1.73,
            "percent": 0.5,
            "calls": 1,
            "input": 120_000,
            "output": 48_000,
            "cache": 680_000,
        },
        {
            "model": "composer-2.5-fast",
            "cost": 1.57,
            "percent": 0.4,
            "calls": 4,
            "input": 180_000,
            "output": 22_000,
            "cache": 1_400_000,
        },
    ]

    def scale(models, cost_f, call_f):
        return [
            {
                **m,
                "cost": round(m["cost"] * cost_f, 2),
                "calls": max(1, round(m["calls"] * call_f)),
            }
            for m in models
        ]

    return {
        "demo": True,
        "fetchedAt": now,
        "user": {
            "id": 0,
            "email": "demo***@example.com",
            "name": "Demo",
            "membership": "Pro",
        },
        "cycle": {"start": cycle_start, "end": cycle_end, "resetAt": cycle_end},
        "quota": {
            "total": 461.25,
            "used": 358.98,
            "remaining": 102.27,
            "gifted": 338.98,
            "usedPercent": 78,
            "remainingPercent": 22,
        },
        "limits": {"cursorModelsPercent": 2, "otherModelsPercent": 0},
        "periods": {
            "today": {"cost": 1.24, "calls": 3, "input": 120000, "output": 18000, "cache": 900000},
            "week": {
                "cost": 50.84,
                "calls": 115,
                "input": 4_200_000,
                "output": 520000,
                "cache": 28_000_000,
            },
            "month": {
                "cost": 392.43,
                "calls": 786,
                "input": 28_000_000,
                "output": 3_600_000,
                "cache": 620_000_000,
            },
            "cycle": {
                "cost": 358.98,
                "calls": 706,
                "input": 22_312_000,
                "output": 3_198_000,
                "cache": 582_180_000,
            },
            "all": {
                "cost": 358.98,
                "calls": 706,
                "input": 22_312_000,
                "output": 3_198_000,
                "cache": 582_180_000,
            },
        },
        "models": {
            "today": [
                {
                    "model": "auto",
                    "cost": 1.1,
                    "percent": 88.7,
                    "calls": 2,
                    "input": 90000,
                    "output": 12000,
                    "cache": 700000,
                },
                {
                    "model": "composer-2.5-fast",
                    "cost": 0.14,
                    "percent": 11.3,
                    "calls": 1,
                    "input": 30000,
                    "output": 6000,
                    "cache": 200000,
                },
            ],
            "week": scale(cycle_models, 0.14, 0.16),
            "month": scale(cycle_models, 1.09, 1.11),
            "cycle": cycle_models,
            "all": cycle_models,
        },
        "events": [
            {
                "time": now - 3600_000,
                "model": "auto",
                "kind": "USAGE_EVENT_KIND_INCLUDED_IN_PRO",
                "cost": 0.42,
                "input": 48000,
                "output": 6200,
                "cache": 210000,
            },
            {
                "time": now - 7200_000,
                "model": "composer-2.5-fast",
                "kind": "USAGE_EVENT_KIND_INCLUDED_IN_PRO",
                "cost": 0.14,
                "input": 30000,
                "output": 6000,
                "cache": 200000,
            },
            {
                "time": now - 10800_000,
                "model": "auto",
                "kind": "USAGE_EVENT_KIND_INCLUDED_IN_PRO",
                "cost": 0.68,
                "input": 82000,
                "output": 9800,
                "cache": 490000,
            },
        ],
        "heatmap": get_demo_heatmap(year),
        "raw": {},
    }
