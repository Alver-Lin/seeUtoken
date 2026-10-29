#!/usr/bin/env python3
"""启动 seeUtoken（会先结束旧进程，避免悬浮窗继续跑旧 UI）。"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _stop_previous() -> None:
    """结束本机仍在运行的 seeUtoken / run.py 实例。"""
    my_pid = os.getpid()
    try:
        out = subprocess.check_output(["ps", "-ax", "-o", "pid=,command="], text=True)
    except Exception:
        return
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        pid_s, cmd = parts
        try:
            pid = int(pid_s)
        except ValueError:
            continue
        if pid == my_pid:
            continue
        if "seeUtoken" not in cmd and "seeutoken" not in cmd:
            continue
        if "run.py" not in cmd and "seeutoken.app" not in cmd and "-m seeutoken" not in cmd:
            continue
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except PermissionError:
            pass


def main() -> None:
    if sys.platform == "win32":
        from seeutoken.windows_runtime import main as windows_main

        raise SystemExit(windows_main())
    _stop_previous()
    os.chdir(ROOT)
    print(f"[seeUtoken] UI 目录: {ROOT / 'ui'}")
    from seeutoken.app import main as app_main

    app_main()


if __name__ == "__main__":
    main()
