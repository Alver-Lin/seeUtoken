"""python -m seeutoken：与 run.py 相同，会先结束旧进程再启动。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import run

run.main()
