"""检测 Cursor 是否在高负载运行（近似 Composer/Agent 工作中）。"""

from __future__ import annotations

import platform
import re
import subprocess
from typing import Any

_CURSOR_NAME = re.compile(r"cursor", re.I)
# 单进程或 Helper 明显飙高时才视为「工作中」，避免 Cursor 前台空闲也转圈
_CPU_MAX_BUSY = 14.0
_CPU_HELPER_BUSY = 10.0
_CPU_TOTAL_BUSY = 24.0
_HELPER = re.compile(r"Cursor Helper", re.I)


def _run(args: list[str], timeout: float = 1.2) -> str:
    try:
        return subprocess.check_output(args, text=True, timeout=timeout).strip()
    except Exception:
        return ""


def _cursor_frontmost() -> bool:
    if platform.system() != "Darwin":
        return False
    name = _run(
        [
            "osascript",
            "-e",
            "tell application \"System Events\" to get name of first application process whose frontmost is true",
        ]
    )
    return bool(name and _CURSOR_NAME.search(name))


def _cursor_processes_running() -> bool:
    if platform.system() != "Darwin":
        return False
    out = _run(["pgrep", "-if", "Cursor"])
    return bool(out)


def _cursor_cpu_stats() -> tuple[float, float, float]:
    """返回 (总 CPU, 单进程峰值, Helper 峰值)。"""
    if platform.system() != "Darwin":
        return 0.0, 0.0, 0.0
    out = _run(["ps", "-A", "-o", "%cpu=", "-o", "comm="])
    total = 0.0
    peak = 0.0
    helper_peak = 0.0
    for line in out.splitlines():
        line = line.strip()
        if not line or not _CURSOR_NAME.search(line):
            continue
        parts = line.split(None, 1)
        if not parts:
            continue
        try:
            cpu = float(parts[0])
        except ValueError:
            continue
        total += cpu
        peak = max(peak, cpu)
        comm = parts[1] if len(parts) > 1 else ""
        if _HELPER.search(comm):
            helper_peak = max(helper_peak, cpu)
    return total, peak, helper_peak


def probe_cursor_activity() -> dict[str, Any]:
    running = _cursor_processes_running()
    frontmost = _cursor_frontmost()
    total, peak, helper_peak = _cursor_cpu_stats()
    busy = False
    if running:
        if peak >= _CPU_MAX_BUSY:
            busy = True
        elif helper_peak >= _CPU_HELPER_BUSY:
            busy = True
        elif total >= _CPU_TOTAL_BUSY:
            busy = True
    return {
        "ok": True,
        "running": running,
        "frontmost": frontmost,
        "cpu": round(total, 1),
        "cpuPeak": round(peak, 1),
        "cpuHelperPeak": round(helper_peak, 1),
        "busy": busy,
    }
