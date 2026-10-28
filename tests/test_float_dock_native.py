"""Opt-in macOS regression with real panels, timers and slide animations.

SEEUTOKEN_NATIVE_TESTS=1 .venv/bin/python -m unittest discover -s tests -p test_float_dock_native.py
Requires access to the macOS window server; does not touch the user's settings.
"""
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from seeutoken.float_dock import FloatDockController, _rect, _timer_target_class, _float_panel_class
from seeutoken.storage import SettingsStore


@unittest.skipUnless(sys.platform == 'darwin' and os.environ.get('SEEUTOKEN_NATIVE_TESTS') == '1',
                     'opt-in test requires the macOS window server')
class NativeFloatDockTests(unittest.TestCase):
    def test_real_appkit_window_passes_only_transparent_parts_and_keeps_hover(self):
        from AppKit import (NSApplication, NSPanel, NSWindowStyleMaskBorderless,
                            NSWindowStyleMaskNonactivatingPanel, NSBackingStoreBuffered, NSMakeRect)
        from Quartz import CGPathCreateMutable, CGPathAddRoundedRect
        from seeutoken.float_dock import Rect

        NSApplication.sharedApplication()
        panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(600, 100, 400, 400),
            NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel,
            NSBackingStoreBuffered, False)
        panel.setReleasedWhenClosed_(False)
        dock = FloatDockController()
        dock._window = panel
        scripts = []
        dock._view = SimpleNamespace(evaluateJavaScript_completionHandler_=lambda script, _: scripts.append(script))
        frame = Rect(600, 100, 400, 400)
        path = CGPathCreateMutable()
        CGPathAddRoundedRect(path, None, NSMakeRect(334, 93, 66, 214), 33, 33)
        dock._input_path = path
        try:
            dock._sync_mouse_input(frame, 800, 300)
            self.assertTrue(panel.ignoresMouseEvents())
            dock._sync_mouse_input(frame, 967, 300)
            self.assertFalse(panel.ignoresMouseEvents())
            self.assertIn('__seeUtokenFloatPointer', scripts[-1])
            dock._sync_mouse_input(frame, 935, 406)  # transparent rounded corner
            self.assertTrue(panel.ignoresMouseEvents())
            # The same path accounting applies to popup, tail and rail together.
            CGPathAddRoundedRect(path, None, NSMakeRect(10, 80, 300, 240), 36, 36)
            dock._sync_mouse_input(frame, 650, 300)
            self.assertFalse(panel.ignoresMouseEvents())
            dock._sync_mouse_input(frame, 650, 480)
            self.assertTrue(panel.ignoresMouseEvents())
        finally:
            dock._window = None
            panel.close()

    def test_topmost_switch_changes_actual_occlusion_order(self):
        from AppKit import (
            NSApplication, NSApplicationActivationPolicyAccessory, NSWindow,
            NSWindowStyleMaskBorderless, NSWindowStyleMaskNonactivatingPanel,
            NSWindowStyleMaskTitled, NSBackingStoreBuffered, NSMakeRect,
            NSNormalWindowLevel, NSStatusWindowLevel, NSScreen,
        )
        from Foundation import NSDate, NSRunLoop
        from Quartz import CGWindowListCopyWindowInfo, kCGWindowListOptionOnScreenOnly, kCGNullWindowID
        from seeutoken.bridge import AppBridge

        app = NSApplication.sharedApplication()
        app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
        app.finishLaunching()
        screen = _rect(NSScreen.mainScreen().visibleFrame())
        frame = NSMakeRect(screen.x + 100, screen.y + 100, 400, 400)
        panel = _float_panel_class().alloc().initWithContentRect_styleMask_backing_defer_(
            frame, NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel,
            NSBackingStoreBuffered, False)
        panel.focus = False
        other = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            frame, NSWindowStyleMaskTitled, NSBackingStoreBuffered, False)
        for window in (panel, other):
            window.setReleasedWhenClosed_(False)
        panel.setHidesOnDeactivate_(False)
        panel.setBecomesKeyOnlyIfNeeded_(True)
        dock = FloatDockController()
        dock._window = panel
        dock._create_handle()
        dock._apply_window_policy()

        def frontmost(first, second):
            ids = [int(w['kCGWindowNumber']) for w in CGWindowListCopyWindowInfo(
                kCGWindowListOptionOnScreenOnly, kCGNullWindowID)]
            a, b = int(first.windowNumber()), int(second.windowNumber())
            return a in ids and b in ids and ids.index(a) < ids.index(b)

        def pump_until(predicate):
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(.03))
                if predicate():
                    return
            self.fail('topmost preference did not change the actual window order')

        try:
            with tempfile.TemporaryDirectory() as tmp, \
                 patch('seeutoken.storage.settings_path', return_value=Path(tmp) / 'settings.json'), \
                 patch('seeutoken.bridge.load_usage_cache', return_value=None):
                bridge = AppBridge(SettingsStore())
                bridge.bind(on_settings_saved=dock.sync)
                app.activateIgnoringOtherApps_(True)
                panel.orderFrontRegardless()
                other.makeKeyAndOrderFront_(None)
                pump_until(lambda: frontmost(panel, other))
                bridge.set_settings({'floatAlwaysOnTop': False})
                # No activation or click on the other window after toggling.
                pump_until(lambda: panel.level() == NSNormalWindowLevel and frontmost(other, panel))
                self.assertFalse(panel.isFloatingPanel())
                bridge.set_settings({'floatAlwaysOnTop': True})
                pump_until(lambda: panel.level() == NSStatusWindowLevel and frontmost(panel, other))
                self.assertTrue(panel.isFloatingPanel())

                # Apply the same behavior to the compact handle while collapsed.
                panel.orderOut_(None)
                dock._collapsed = True
                dock._handle.setFrame_display_(NSMakeRect(frame.origin.x, frame.origin.y, 12, 56), True)
                dock._order_panel(dock._handle)
                pump_until(lambda: frontmost(dock._handle, other))
                bridge.set_settings({'floatAlwaysOnTop': False})
                pump_until(lambda: dock._handle.level() == NSNormalWindowLevel and frontmost(other, dock._handle))
                bridge.set_settings({'floatAlwaysOnTop': True})
                pump_until(lambda: dock._handle.level() == NSStatusWindowLevel and frontmost(dock._handle, other))
        finally:
            dock.dispose()
            for window in (panel, other):
                window.orderOut_(None)
                window.close()

    def test_live_settings_control_real_panels_on_both_edges(self):
        from AppKit import (
            NSApplication, NSApplicationActivationPolicyProhibited, NSPanel,
            NSWindowStyleMaskBorderless, NSWindowStyleMaskNonactivatingPanel,
            NSBackingStoreBuffered, NSColor, NSMakeRect, NSScreen,
        )
        from Foundation import NSDate, NSRunLoop, NSRunLoopCommonModes, NSTimer
        from seeutoken.bridge import AppBridge

        app = NSApplication.sharedApplication()
        app.setActivationPolicy_(NSApplicationActivationPolicyProhibited)
        app.finishLaunching()
        screen = _rect(NSScreen.mainScreen().visibleFrame())
        pointer = SimpleNamespace(x=screen.x + screen.width / 2, y=screen.y + 5)

        def pump_until(predicate, timeout=2):
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(.02))
                if predicate():
                    return
            self.fail('native window transition did not finish')

        def pump_for(seconds):
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(.02))

        for edge in ('left', 'right'):
            with self.subTest(edge=edge), tempfile.TemporaryDirectory() as tmp, \
                 patch('seeutoken.storage.settings_path', return_value=Path(tmp) / 'settings.json'), \
                 patch('AppKit.NSEvent', SimpleNamespace(mouseLocation=lambda: pointer)), \
                 patch('seeutoken.bridge.load_usage_cache', return_value=None):
                store = SettingsStore()
                bridge = AppBridge(store)
                dock = FloatDockController(settings=store.get())
                panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
                    NSMakeRect(screen.x + screen.width / 2 - 200, screen.y + 100, 400, 400),
                    NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel,
                    NSBackingStoreBuffered, False,
                )
                panel.setReleasedWhenClosed_(False)
                panel.setHidesOnDeactivate_(False)
                panel.setOpaque_(False)
                panel.setBackgroundColor_(NSColor.clearColor())
                panel.setTitle_('seeUtoken edge behavior verification')
                dock._window = panel
                dock._expanded = _rect(panel.frame())
                dock._view = SimpleNamespace(evaluateJavaScript_completionHandler_=lambda *args: None)
                dock._create_handle()
                dock._apply_window_policy()
                bridge.bind(on_settings_saved=dock.sync)
                dock._target = _timer_target_class().alloc().init()
                dock._target.controller = dock
                dock._timer = NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(
                    .04, dock._target, 'tick:', None, True)
                NSRunLoop.mainRunLoop().addTimer_forMode_(dock._timer, NSRunLoopCommonModes)
                try:
                    panel.orderFrontRegardless()
                    bridge.set_settings({'floatAutoHide': False})
                    pump_until(lambda: not dock._auto_hide)
                    frame = _rect(panel.frame())
                    target_x = screen.x - 334 if edge == 'left' else screen.right - 400
                    dock.set_dragging(True)
                    dock.move_by(target_x - frame.x, 0)
                    dock.set_dragging(False)
                    self.assertEqual(dock._edge, edge)
                    expanded = _rect(panel.frame())
                    pump_for(dock.HIDE_DELAY + .3)
                    self.assertFalse(dock._collapsed)
                    self.assertTrue(panel.isVisible())
                    self.assertFalse(dock._handle.isVisible())

                    bridge.set_settings({'floatAutoHide': True})
                    pump_until(lambda: dock._collapsed and not panel.isVisible())
                    self.assertTrue(dock._handle.isVisible())
                    offscreen = _rect(panel.frame())
                    self.assertAlmostEqual(abs(offscreen.x - expanded.x), 76, delta=1)
                    self.assertEqual(offscreen.width, expanded.width)

                    tab = _rect(dock._handle.frame())
                    pointer.x, pointer.y = tab.x + tab.width / 2, tab.y + tab.height / 2
                    pump_until(lambda: not dock._collapsed and time.monotonic() >= dock._animating_until)
                    self.assertTrue(panel.isVisible())
                    self.assertFalse(dock._handle.isVisible())
                    self.assertAlmostEqual(_rect(panel.frame()).x, expanded.x, delta=1)

                    pointer.x, pointer.y = screen.x + screen.width / 2, screen.y + 5
                    pump_until(lambda: dock._collapsed and not panel.isVisible())
                    bridge.set_settings({'floatAutoHide': False})
                    pump_until(lambda: not dock._collapsed and time.monotonic() >= dock._animating_until)
                    pump_for(dock.HIDE_DELAY + .3)
                    self.assertTrue(panel.isVisible())
                    self.assertFalse(dock._handle.isVisible())
                    self.assertFalse(dock._collapsed)
                    self.assertFalse(SettingsStore().get()['floatAutoHide'])
                finally:
                    dock.dispose()
                    panel.orderOut_(None)
                    panel.close()


if __name__ == '__main__':
    unittest.main()
