import ctypes
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from seeutoken.float_dock import Rect
from seeutoken.windows_float_dock import WindowsFloatDockController, _WinFormsHost, handle_frame


class Host:
    def __init__(self, frame=Rect(600, 100, 400, 400), scale=1):
        self.frame, self.scale = frame, scale
        self.screen_list = [Rect(0, 0, 1000, 800)]
        self.point = (400, 700)
        self.shown = {False: True, True: False}
        self.handle = None
        self.states = []
        self.levels = []
        self.disposed = False

    @property
    def client_size(self): return self.frame.width, self.frame.height
    @property
    def client_origin(self): return self.frame.x, self.frame.y
    def invoke(self, fn): return fn()
    def screens(self): return self.screen_list
    def pointer(self): return self.point
    def visible(self, handle=False): return self.shown[handle]
    def move(self, frame, handle=False):
        if handle: self.handle = frame
        else: self.frame = frame
    def show(self, visible, handle=False): self.shown[handle] = bool(visible)
    def topmost(self, enabled): self.levels.append(enabled)
    def script(self, script):
        self.states.append(json.loads(script.split('=', 1)[1].split(';', 1)[0]))
    def dispose(self): self.disposed = True; self.shown = {False: False, True: False}


class WindowsDockTests(unittest.TestCase):
    def setUp(self):
        self.now = 10
        clock = patch('seeutoken.windows_float_dock.time.monotonic', lambda: self.now)
        clock.start()
        self.addCleanup(clock.stop)
        self.dock = WindowsFloatDockController()
        self.host = Host()
        self.dock._host = self.host
        self.dock.set_visible(True)

    def collapse(self):
        self.dock.tick()
        self.now += .2
        self.dock.tick()
        self.now += .7
        self.dock.tick()
        self.assertTrue(self.dock._collapsed)

    def test_right_edge_collapses_and_hover_reveals_without_resizing_webview(self):
        original = self.host.frame
        self.collapse()
        self.assertEqual(self.host.handle, Rect(988, 272, 12, 56))
        self.assertEqual(self.host.shown, {False: False, True: True})
        self.assertEqual(self.host.frame, original)
        self.assertTrue(self.host.states[-1]['nativeHandle'])
        self.host.point = (995, 300)
        self.dock.tick()
        self.assertFalse(self.dock._collapsed)
        self.assertEqual(self.host.shown, {False: True, True: False})
        self.assertEqual(self.host.frame, original)

    def test_negative_monitor_coordinates_and_150_percent_scaling(self):
        self.host.frame, self.host.scale = Rect(-2001, 100, 600, 600), 1.5
        self.host.screen_list = [Rect(-1500, -100, 1500, 1000), Rect(0, 0, 1200, 800)]
        self.collapse()
        self.assertEqual(self.dock._edge, 'left')
        self.assertEqual(self.host.frame, Rect(-1500, 100, 600, 600))
        self.assertEqual(self.host.handle, Rect(-1500, 358, 18, 84))
        self.host.point = (-1491, 400)
        self.dock.tick()
        self.assertTrue(self.host.visible())

    def test_dragging_off_left_edge_preserves_rail_position_and_stays_open(self):
        self.host.frame = Rect(-334, 100, 400, 400)
        self.collapse()
        self.dock.set_dragging(True)
        self.dock.move_by(120, 30)
        self.dock.set_dragging(False)
        self.assertIsNone(self.dock._edge)
        self.assertEqual(self.dock._rail().x, 120)
        self.assertEqual(self.host.frame.y, 130)
        self.now += 100
        self.dock.tick()
        self.assertTrue(self.host.visible())
        self.assertFalse(self.dock._collapsed)

    def test_popup_hit_regions_prevent_auto_hide_and_transparent_reserve_does_not(self):
        geometry = {'width': 400, 'height': 400,
                    'railRect': {'x': 334, 'y': 93, 'width': 66, 'height': 214},
                    'hitRects': [{'x': 10, 'y': 50, 'width': 300, 'height': 300}]}
        self.dock.update_geometry(geometry)
        self.dock.tick()
        self.assertIs(self.dock._geometry, geometry)  # unchanged layout needs no duplicate JS report
        self.host.point = (650, 180)
        self.now += 20
        self.dock.tick()
        self.assertIsNone(self.dock._hide_at)
        self.host.point = (920, 110)  # transparent reserve, outside popup and rail
        self.dock.tick()
        self.now += .7
        self.dock.tick()
        self.assertTrue(self.dock._collapsed)

    def test_disabling_auto_hide_reveals_immediately_and_respects_visibility(self):
        self.collapse()
        self.dock.sync({'floatAutoHide': False, 'floatAlwaysOnTop': False})
        self.assertFalse(self.dock._collapsed)
        self.assertTrue(self.host.visible())
        self.assertEqual(self.host.levels[-1], False)
        self.now += 100
        self.dock.tick()
        self.assertFalse(self.dock._collapsed)
        self.dock.set_visible(False)
        self.dock.sync({'floatAutoHide': False})
        self.assertEqual(self.host.shown, {False: False, True: False})

    def test_hidden_collapsed_dock_cannot_reappear_on_mouse_hover(self):
        self.collapse()
        self.dock.set_visible(False)
        self.host.point = (995, 300)
        self.dock.tick()
        self.assertEqual(self.host.shown, {False: False, True: False})
        self.dock.set_visible(True)
        self.assertEqual(self.host.shown, {False: False, True: True})

    def test_dragging_suspends_hiding_and_click_without_movement_keeps_docking(self):
        self.dock.tick()
        self.dock.set_dragging(True)
        self.now += 100
        self.dock.tick()
        self.assertFalse(self.dock._collapsed)
        self.dock.set_dragging(False)
        self.assertEqual(self.dock._edge, 'right')

    def test_dom_coordinates_scale_at_200_percent_and_stale_geometry_is_ignored(self):
        self.host.frame, self.host.scale = Rect(400, 100, 800, 800), 2
        geometry = {'width': 400, 'height': 400, 'hitRects': [],
                    'railRect': {'x': 334, 'y': 93, 'width': 66, 'height': 214}}
        self.dock.update_geometry(geometry)
        self.assertEqual(self.dock._rail(), Rect(1068, 286, 132, 428))
        self.dock.update_geometry({**geometry, 'width': 300})
        self.assertIs(self.dock._geometry, geometry)
        self.dock.move_by(10, -5)
        self.assertEqual(self.host.frame, Rect(420, 90, 800, 800))

    def test_removing_monitor_restores_collapsed_window_to_remaining_work_area(self):
        self.collapse()
        self.host.screen_list = [Rect(-800, 0, 800, 560)]
        self.dock.tick()
        self.assertFalse(self.dock._collapsed)
        self.assertIsNone(self.dock._edge)
        self.assertEqual(self.host.frame, Rect(-400, 100, 400, 400))
        self.assertTrue(self.host.visible())

    def test_persistence_uses_logical_pixels_and_shutdown_releases_both_windows(self):
        self.host.frame, self.host.scale = Rect(400, 100, 800, 800), 2
        self.dock._expanded = self.host.frame
        self.dock._persist = Mock()
        thread = lambda target, args, daemon: SimpleNamespace(start=lambda: target(*args))
        with patch('seeutoken.windows_float_dock.threading.Thread', side_effect=thread):
            self.dock._save()
            self.dock._save()
        self.dock._persist.assert_called_once_with(200, 50)
        self.dock.dispose()
        self.assertTrue(self.host.disposed)
        self.assertFalse(self.dock.attached)

    def test_handle_is_clamped_inside_small_work_area(self):
        frame = handle_frame(Rect(0, -100, 400, 400), 214, 'right', Rect(0, 0, 20, 30), 2)
        self.assertEqual(frame, Rect(0, 0, 20, 30))


class WindowsHostTests(unittest.TestCase):
    def test_initialization_failure_releases_native_handle_and_keeps_sidebar_fallback(self):
        host = Mock()
        host.invoke.side_effect = lambda work: work()
        host.start.side_effect = RuntimeError('timer unavailable')
        dock = WindowsFloatDockController()
        with patch('seeutoken.windows_float_dock._WinFormsHost', return_value=host), \
                self.assertLogs(level='ERROR'):
            dock.attach(SimpleNamespace(native=object()))
        host.dispose.assert_called_once()
        self.assertFalse(dock.attached)

    def test_move_and_show_preserve_64_bit_handle_and_never_activate(self):
        host = _WinFormsHost.__new__(_WinFormsHost)
        host.form = SimpleNamespace(IsDisposed=False, Handle=SimpleNamespace(ToInt64=lambda: 0x100000001))
        host.user = Mock()
        host.user.IsWindowVisible.return_value = False
        host.move(Rect(-1200, 100, 600, 600))
        host.user.SetWindowPos.assert_called_once_with(0x100000001, None, -1200, 100, 600, 600, 0x14)
        host.show(True)
        host.user.ShowWindow.assert_called_once_with(0x100000001, 4)

    def test_cross_thread_work_uses_form_invoke_and_webview_scripts_are_nonblocking(self):
        host = _WinFormsHost.__new__(_WinFormsHost)
        host.form = Mock(InvokeRequired=True, IsDisposed=False)
        host.form.Invoke.side_effect = lambda work: work()
        with patch.dict('sys.modules', {'System': SimpleNamespace(Action=lambda fn: fn)}):
            self.assertEqual(host.invoke(lambda: 42), 42)
        host.form.Invoke.assert_called_once()
        host.script('window.test=1')
        host.form.webview.ExecuteScriptAsync.assert_called_once_with('window.test=1')

    def test_app_selects_windows_controller_and_does_not_activate_collapsed_sidebar(self):
        from seeutoken.app import SeeUtokenApp

        store = SimpleNamespace(get=lambda: {}, save=Mock())
        with patch('seeutoken.app.sys.platform', 'win32'), \
                patch('seeutoken.app.SettingsStore', return_value=store), \
                patch('seeutoken.app.AppBridge'), \
                patch('seeutoken.app.FloatNativeMaterialController'), \
                patch('seeutoken.app.MainNativeMaterialController'), \
                patch('seeutoken.app.FloatPointerController'):
            app = SeeUtokenApp()
            self.assertIsInstance(app.float_dock, WindowsFloatDockController)
            app.float_dock = Mock(attached=True)
            app.float_win = Mock()
            app._float_ready = True
            app._set_float_visible(True)
            app.float_dock.set_visible.assert_called_once_with(True)
            app.float_win.show.assert_not_called()
            app.float_win.hide.assert_not_called()


if __name__ == '__main__':
    unittest.main()
