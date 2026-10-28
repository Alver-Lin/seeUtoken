"""macOS 触控板触觉反馈（悬浮窗图标切换等）。"""

from __future__ import annotations

import sys
import time
from typing import Literal

HapticKind = Literal["generic", "alignment", "level", "hover", "max"]

# NSHapticFeedbackPatternGeneric = 0
# NSHapticFeedbackPatternAlignment = 1
# NSHapticFeedbackPatternLevelChange = 2（通常最强）
_PATTERN = {
    "generic": 0,
    "alignment": 1,
    "level": 2,
    "hover": 2,
    "max": 2,
}

# NSHapticFeedbackPerformanceTimeNow = 1
_PERFORMANCE_TIME = 1

# 切换图标：以 LevelChange 为主的三连击（系统允许范围内最强）
_HOVER_PULSE_GAP_S = 0.052
_HOVER_PULSE_SEQUENCE = (2, 2, 1)


def _fire(pattern: int) -> None:
    from AppKit import NSHapticFeedbackManager

    performer = NSHapticFeedbackManager.defaultPerformer()
    performer.performFeedbackPattern_performanceTime_(pattern, _PERFORMANCE_TIME)


def _fire_hover() -> None:
    for i, pattern in enumerate(_HOVER_PULSE_SEQUENCE):
        _fire(pattern)
        if i < len(_HOVER_PULSE_SEQUENCE) - 1:
            time.sleep(_HOVER_PULSE_GAP_S)


def _fire_max() -> None:
    """显式最强：两档变化 + 对齐 + 再一档变化。"""
    for i, pattern in enumerate((2, 2, 1, 2)):
        _fire(pattern)
        if i < 3:
            time.sleep(_HOVER_PULSE_GAP_S)


def _run_on_main(block) -> None:
    try:
        from Foundation import NSOperationQueue, NSThread

        if NSThread.isMainThread():
            block()
            return
        NSOperationQueue.mainQueue().addOperationBlock_(block)
        return
    except Exception:
        pass

    try:
        from PyObjCTools import AppHelper

        if AppHelper.running():
            AppHelper.callAfter(block)
            return
    except Exception:
        pass

    block()


def perform_haptic(kind: HapticKind | str = "hover") -> bool:
    if sys.platform != "darwin":
        return False

    key = str(kind or "hover").lower()
    pattern = _PATTERN.get(key, _PATTERN["hover"])

    def work() -> None:
        try:
            if key in ("hover", "max"):
                _fire_max() if key == "max" else _fire_hover()
            else:
                _fire(pattern)
        except Exception:
            pass

    try:
        _run_on_main(work)
        return True
    except Exception:
        return False
