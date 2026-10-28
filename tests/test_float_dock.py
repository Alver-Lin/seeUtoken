import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from seeutoken.float_dock import Rect, FloatDockController, edge_for, collapsed_frame, _use_overlay_panel
from seeutoken.storage import SettingsStore


def native_rect(rect):
    return types.SimpleNamespace(origin=types.SimpleNamespace(x=rect.x, y=rect.y),
                                 size=types.SimpleNamespace(width=rect.width, height=rect.height))


class Window:
    def __init__(self, rect):
        self.rect, self.visible = rect, True
        self.order = None
        self.behavior = 0
    def frame(self): return native_rect(self.rect)
    def isVisible(self): return self.visible
    def orderOut_(self, sender): self.visible = False
    def orderFrontRegardless(self): self.visible, self.order = True, 'front'
    def orderBack_(self, sender): self.visible, self.order = True, 'back'
    def setFrame_display_(self, frame, display): self.rect = frame
    def setFrameOrigin_(self, point): self.rect = Rect(*point, self.rect.width, self.rect.height)
    def setLevel_(self, level): self.level = level
    def setFloatingPanel_(self, floating): self.floating = floating
    def setIgnoresMouseEvents_(self, ignore): self.ignores_mouse_events = ignore
    def collectionBehavior(self): return self.behavior
    def setCollectionBehavior_(self, behavior): self.behavior = behavior
    def animator(self): return self


class FloatDockTests(unittest.TestCase):
    def setUp(self):
        self.now = 10.0
        self.mouse = types.SimpleNamespace(x=400, y=700)
        self.screen = types.SimpleNamespace(visibleFrame=lambda: native_rect(Rect(0, 0, 1000, 800)))
        self.appkit = types.SimpleNamespace(
            NSEvent=types.SimpleNamespace(mouseLocation=lambda: self.mouse),
            NSScreen=types.SimpleNamespace(screens=lambda: [self.screen]),
            NSMakeRect=Rect,
            NSNormalWindowLevel=0,
            NSStatusWindowLevel=25,
            NSWindowCollectionBehaviorCanJoinAllSpaces=1,
            NSWindowCollectionBehaviorFullScreenAuxiliary=256,
            NSWindowCollectionBehaviorMoveToActiveSpace=2,
        )
        self.patches = [patch.dict(sys.modules, {'AppKit': self.appkit}),
                        patch('seeutoken.float_dock.sys.platform', 'darwin'),
                        patch('seeutoken.float_dock.time.monotonic', lambda: self.now),
                        patch('seeutoken.float_dock._run_on_main', lambda fn: fn())]
        for item in self.patches: item.start()
        self.dock = FloatDockController()
        self.dock._window = Window(Rect(600, 100, 400, 400))
        self.dock._handle = Window(Rect(0, 0, 12, 56))
        self.dock._view = types.SimpleNamespace(evaluateJavaScript_completionHandler_=lambda *args: None)
        self.slides = []
        def slide(frame, duration, completion=None):
            self.slides.append((frame, duration))
            self.dock._window.rect = frame
            if completion: completion()
        self.dock._slide = slide

    def tearDown(self):
        for item in reversed(self.patches): item.stop()

    def collapse(self):
        self.dock.tick()  # snap
        self.now += .4
        self.dock.tick()  # schedule
        self.now += .7
        self.dock.tick()  # collapse

    def test_right_edge_hides_real_window_and_hover_restores(self):
        self.collapse()
        self.assertTrue(self.dock._collapsed)
        self.assertEqual(self.dock._handle.rect, Rect(988, 272, 12, 56))
        self.assertFalse(self.dock._window.visible)
        self.assertEqual(self.dock._window.rect.width, 400)
        self.mouse.x, self.mouse.y = 995, 300
        self.now += .4
        self.dock.tick()
        self.assertFalse(self.dock._collapsed)
        self.assertEqual(self.dock._window.rect, Rect(600, 100, 400, 400))
        self.assertTrue(self.dock._window.visible)
        self.assertFalse(self.dock._handle.visible)

    def test_drag_away_remains_open_after_mouse_leaves(self):
        self.collapse()
        self.dock.set_dragging(True)
        self.dock.move_by(-100, 0)
        self.dock.set_dragging(False)
        self.assertIsNone(self.dock._edge)
        self.now += 100
        self.dock.tick()
        self.assertFalse(self.dock._collapsed)
        self.assertEqual(self.dock._window.rect.width, 400)

    def test_left_edge_and_detach_preserve_rail_position(self):
        self.dock._window.rect = Rect(-334, 100, 400, 400)
        self.collapse()
        self.assertEqual(self.dock._edge, 'left')
        self.assertEqual(self.dock._handle.rect.x, 0)
        self.dock.set_dragging(True)
        self.dock.move_by(120, 0)
        self.dock.set_dragging(False)
        self.assertIsNone(self.dock._edge)
        self.assertEqual(self.dock._window.rect.right - 66, 120)

    def test_staying_inside_popup_prevents_hide(self):
        self.dock.tick()
        self.dock.update_geometry({'width': 400, 'height': 400,
                                  'railRect': {'x': 334, 'y': 93, 'width': 66, 'height': 214},
                                  'hitRects': [{'x': 4, 'y': 30, 'width': 300, 'height': 320}]})
        self.mouse.x, self.mouse.y = 650, 300
        self.now += 50
        self.dock.tick()
        self.assertFalse(self.dock._collapsed)
        self.assertIsNone(self.dock._hide_at)

    def test_transparent_reserve_passes_clicks_but_icons_and_popup_remain_interactive(self):
        self.dock._auto_hide = False
        self.dock._edge = 'right'
        geometry = {'width': 400, 'height': 400,
                    'railRect': {'x': 334, 'y': 93, 'width': 66, 'height': 214},
                    'hitRects': [{'x': 334, 'y': 93, 'width': 66, 'height': 214}]}
        self.dock.update_geometry(geometry)
        self.mouse.x, self.mouse.y = 800, 300  # invisible reserve above another app's button
        self.dock.tick()
        self.assertTrue(self.dock._window.ignores_mouse_events)
        self.mouse.x, self.mouse.y = 967, 300  # visible rail
        self.dock.tick()
        self.assertFalse(self.dock._window.ignores_mouse_events)
        geometry['hitRects'].append({'x': 10, 'y': 50, 'width': 300, 'height': 300})
        self.dock.update_geometry(geometry)
        self.mouse.x, self.mouse.y = 650, 300  # expanded popup
        self.dock.tick()
        self.assertFalse(self.dock._window.ignores_mouse_events)
        self.mouse.x, self.mouse.y = 650, 480  # above the expanded popup
        self.dock.tick()
        self.assertTrue(self.dock._window.ignores_mouse_events)

    def test_clickthrough_preserves_hover_and_does_not_break_dragging_outside_window(self):
        scripts = []
        self.dock._view.evaluateJavaScript_completionHandler_ = lambda script, _: scripts.append(script)
        self.dock._edge = 'right'
        self.dock._auto_hide = False
        self.mouse.x, self.mouse.y = 800, 300
        self.dock.tick()
        self.assertTrue(self.dock._window.ignores_mouse_events)
        self.assertEqual(json.loads(scripts[-1].split('?.(', 1)[1][:-2]), {'x': 200, 'y': 200})
        self.mouse.x, self.mouse.y = 967, 300
        self.dock.tick()
        self.assertFalse(self.dock._window.ignores_mouse_events)
        self.assertEqual(json.loads(scripts[-1].split('?.(', 1)[1][:-2]), {'x': 367, 'y': 200})
        self.dock.set_dragging(True)
        self.mouse.x, self.mouse.y = 500, 700
        self.dock.tick()
        self.assertFalse(self.dock._window.ignores_mouse_events)
        self.dock.set_dragging(False)
        self.assertTrue(self.dock._window.ignores_mouse_events)
        self.assertIn('(null)', scripts[-1])

    def test_dragging_disables_auto_hide(self):
        self.dock.tick()
        self.dock.set_dragging(True)
        self.now += 50
        self.dock.tick()
        self.assertFalse(self.dock._collapsed)

    def test_webview_keeps_full_geometry_while_handle_is_showing(self):
        self.collapse()
        self.dock.update_geometry({'width': 400, 'height': 400, 'hitRects': []})
        self.assertEqual(self.dock._geometry['width'], 400)
        self.assertEqual(self.dock._window.rect.width, 400)

    def test_hide_preference_hides_handle_and_stops_hover_reveal(self):
        self.collapse()
        self.dock.set_visible(False)
        self.mouse.x, self.mouse.y = 995, 300
        self.now += 1
        self.dock.tick()
        self.assertTrue(self.dock._collapsed)
        self.assertFalse(self.dock._handle.visible)
        self.dock.set_visible(True)
        self.dock.tick()
        self.assertFalse(self.dock._collapsed)

    def test_reveal_and_collapse_use_short_native_slides_without_resizing(self):
        self.collapse()
        self.assertEqual(self.slides[-1][1], .14)
        self.dock.reveal()
        self.assertEqual(self.slides[-1][1], .18)
        self.assertTrue(all(frame.width == 400 and frame.height == 400 for frame, _ in self.slides))

    def test_slide_uses_appkit_animation_context_and_runs_completion(self):
        completed = []
        durations = []
        context = types.SimpleNamespace(setDuration_=durations.append, setTimingFunction_=lambda value: None)
        def animate(group, completion):
            group(context)
            completion()
        self.appkit.NSAnimationContext = types.SimpleNamespace(runAnimationGroup_completionHandler_=animate)
        quartz = types.SimpleNamespace(CAMediaTimingFunction=types.SimpleNamespace(functionWithName_=lambda name: name))
        target = Rect(676, 100, 400, 400)
        with patch.dict(sys.modules, {'Foundation': types.SimpleNamespace(), 'Quartz': quartz}):
            FloatDockController._slide(self.dock, target, .14, lambda: completed.append(True))
        self.assertEqual(self.dock._window.rect, target)
        self.assertEqual(durations, [.14])
        self.assertEqual(completed, [True])

    def test_auto_hide_can_be_disabled_and_reenabled_while_docked(self):
        self.dock.sync({'floatAutoHide': False})
        self.collapse()
        self.assertEqual(self.dock._edge, 'right')
        self.assertFalse(self.dock._collapsed)
        self.assertIsNone(self.dock._hide_at)
        self.dock.sync({'floatAutoHide': True})
        self.now += 1
        self.dock.tick()
        self.now += 1
        self.dock.tick()
        self.assertTrue(self.dock._collapsed)

    def test_disabling_auto_hide_restores_collapsed_rail(self):
        self.collapse()
        self.dock.sync({'floatAutoHide': False})
        self.assertFalse(self.dock._collapsed)
        self.assertTrue(self.dock._window.visible)
        self.assertFalse(self.dock._handle.visible)
        self.assertEqual(self.dock._window.rect, Rect(600, 100, 400, 400))
        self.now += 100
        self.dock.tick()
        self.assertFalse(self.dock._collapsed)

    def test_disabling_auto_hide_does_not_show_hidden_rail(self):
        self.collapse()
        self.dock.set_visible(False)
        self.dock.sync({'floatAutoHide': False})
        self.assertFalse(self.dock._collapsed)
        self.assertFalse(self.dock._window.visible)
        self.assertFalse(self.dock._handle.visible)
        self.assertEqual(self.dock._window.rect, Rect(600, 100, 400, 400))

    def test_topmost_updates_expanded_rail_and_collapsed_handle(self):
        self.collapse()
        self.dock.sync({'floatAlwaysOnTop': False})
        self.assertEqual(self.dock._window.level, 0)
        self.assertEqual(self.dock._handle.level, 0)
        self.assertEqual(self.dock._handle.order, 'back')
        self.assertFalse(self.dock._handle.floating)
        self.assertEqual(self.dock._handle.behavior & 256, 0)
        self.assertTrue(self.dock._collapsed)
        self.dock.sync({'floatAlwaysOnTop': True})
        self.assertEqual(self.dock._window.level, 25)
        self.assertEqual(self.dock._handle.level, 25)
        self.assertEqual(self.dock._handle.order, 'front')
        self.assertTrue(self.dock._handle.floating)
        self.assertEqual(self.dock._handle.behavior & 256, 256)
        self.assertTrue(self.dock._collapsed)

    def test_topmost_choice_applies_immediately_and_survives_show_and_reveal(self):
        self.dock._handle.visible = False
        self.dock.sync({'floatAlwaysOnTop': False})
        self.assertEqual(self.dock._window.order, 'back')
        self.assertFalse(self.dock._handle.visible)
        self.dock._window.order = None
        self.dock.sync({'floatAlwaysOnTop': False, 'floatGlassStyle': 'frosted'})
        self.assertIsNone(self.dock._window.order)
        self.dock.set_visible(True)
        self.assertEqual(self.dock._window.order, 'back')
        self.collapse()
        self.assertEqual(self.dock._handle.order, 'back')
        self.dock.reveal()
        self.assertEqual(self.dock._window.order, 'back')
        self.dock.sync({'floatAlwaysOnTop': True})
        self.assertEqual(self.dock._window.order, 'front')

    def test_changing_topmost_does_not_show_hidden_windows(self):
        self.dock.set_visible(False)
        self.dock._window.visible = False
        self.dock.sync({'floatAlwaysOnTop': False})
        self.assertFalse(self.dock._window.visible)
        self.assertFalse(self.dock._handle.visible)

    def test_saved_behavior_is_restored_and_old_settings_keep_defaults(self):
        with tempfile.TemporaryDirectory() as tmp, patch('seeutoken.storage.settings_path', return_value=Path(tmp) / 'settings.json'):
            old = FloatDockController(settings=SettingsStore().get())
            self.assertTrue(old._auto_hide)
            self.assertTrue(old._always_on_top)
            SettingsStore().save({'floatAutoHide': False, 'floatAlwaysOnTop': False})
            restored = FloatDockController(settings=SettingsStore().get())
            self.assertFalse(restored._auto_hide)
            self.assertFalse(restored._always_on_top)

    def test_multi_monitor_negative_origins_and_threshold(self):
        screens = [Rect(-1200, 0, 1200, 900), Rect(0, 0, 1000, 800)]
        edge, screen = edge_for(Rect(-1195, 300, 66, 214), screens)
        self.assertEqual(edge, 'left')
        self.assertEqual(screen, screens[0])
        self.assertEqual(edge_for(Rect(100, 300, 66, 214), screens), (None, None))
        tab = collapsed_frame(Rect(-1200, 0, 400, 400), 214, edge, screen)
        self.assertEqual(tab.x, -1200)
        self.assertEqual(tab.width, 12)
        self.assertEqual(tab.height, 56)

    def test_fullscreen_panel_transfer_preserves_webview_and_delegate(self):
        calls = []
        content = types.SimpleNamespace(bounds=lambda: native_rect(Rect(0, 0, 400, 400)))
        delegate = object()
        class Panel:
            focus = True
            @classmethod
            def alloc(cls): return cls()
            def initWithContentRect_styleMask_backing_defer_(self, *args): return self
            def initWithFrame_(self, frame): return self
            def isKindOfClass_(self, cls): return isinstance(self, cls)
            def isVisible(self): return True
            def __getattr__(self, name):
                return lambda *args: calls.append((name, args))
        class Old(Window):
            focus = True
            def isKindOfClass_(self, cls): return False
            def title(self): return 'seeUtoken float'
            def delegate(self): return delegate
            def contentView(self): return content
            def setDelegate_(self, value): calls.append(('old-delegate', value))
            def setContentView_(self, view): calls.append(('old-content', view))
            def close(self): calls.append(('old-closed', None))
        fake_appkit = types.SimpleNamespace(NSPanel=Panel, NSView=Panel,
            NSColor=types.SimpleNamespace(clearColor=lambda: None), NSBackingStoreBuffered=2,
            NSWindowStyleMaskBorderless=0, NSWindowStyleMaskNonactivatingPanel=128)
        webview = object()
        browser = types.SimpleNamespace(window=Old(Rect(600, 100, 400, 400)), webview=webview,
                                        pywebview_window=types.SimpleNamespace(native=None))
        with patch.dict(sys.modules, {'AppKit': fake_appkit}), patch('seeutoken.float_dock._float_panel_class', lambda: Panel):
            panel, visible = _use_overlay_panel(browser)
            self.assertTrue(visible)
            self.assertIs(browser.window, panel)
            self.assertIs(browser.pywebview_window.native, panel)
            self.assertIs(browser.webview, webview)
            self.assertIn(('setContentView_', (content,)), calls)
            self.assertIn(('setDelegate_', (delegate,)), calls)
            self.assertLess(calls.index(('old-delegate', None)), calls.index(('old-closed', None)))
            previous_count = len(calls)
            self.assertIs(_use_overlay_panel(browser)[0], panel)
            self.assertEqual(len(calls), previous_count)


if __name__ == '__main__': unittest.main()
