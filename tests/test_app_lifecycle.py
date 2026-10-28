import sys
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

from seeutoken.app import SeeUtokenApp
from seeutoken.mac_lifecycle import install_app_delegate


class AppLifecycleTests(unittest.TestCase):
    def app(self):
        app = SeeUtokenApp.__new__(SeeUtokenApp)
        app._quitting = False
        app.main_win, app.float_win = Mock(), Mock()
        app.main_native, app.float_native = Mock(), Mock()
        app.float_pointer, app.float_dock = Mock(), Mock()
        app._refresh_stop, app._login_poll_stop = threading.Event(), threading.Event()
        app._close_login_win = Mock()
        app._ui_server, app._tray = Mock(), Mock()
        return app

    def test_red_close_shuts_down_every_window_without_stopping_appkit_early(self):
        app = self.app()
        login = Mock()
        with patch('seeutoken.app.sys.platform', 'darwin'), \
                patch('seeutoken.app._run_on_main', lambda fn: fn()), \
                patch('seeutoken.app.webview.windows', [app.main_win, app.float_win, login]):
            self.assertFalse(app._handle_main_closing())
            self.assertTrue(app._quitting)
            self.assertTrue(app._refresh_stop.is_set())
            self.assertTrue(app._login_poll_stop.is_set())
            for controller in (app.main_native, app.float_native, app.float_pointer, app.float_dock):
                controller.dispose.assert_called_once()
            for window in (app.main_win, app.float_win, login):
                window.destroy.assert_called_once()
            self.assertFalse(app._tray.visible)
            app._tray.stop.assert_not_called()
            app._ui_server.shutdown.assert_called_once()
            app._ui_server.server_close.assert_called_once()
            self.assertTrue(app._handle_main_closing())
            app._quit()
            app.main_win.destroy.assert_called_once()

    def test_failed_material_cleanup_does_not_leave_sidebar_running(self):
        app = self.app()
        app.main_native.dispose.side_effect = RuntimeError('already disposed')
        with patch('seeutoken.app.sys.platform', 'win32'), \
                patch('seeutoken.app.webview.windows', [app.main_win, app.float_win]):
            app._quit()
        app.float_dock.dispose.assert_called_once()
        app.float_win.destroy.assert_called_once()
        app._tray.stop.assert_called_once()

    def test_restore_unminimizes_unhides_activates_and_focuses_main_window(self):
        app = self.app()
        ns, native_app = Mock(), Mock()
        ns.isMiniaturized.return_value = True
        actions = Mock()
        actions.attach_mock(ns, 'window')
        actions.attach_mock(native_app, 'application')
        appkit = SimpleNamespace(NSApplication=SimpleNamespace(sharedApplication=lambda: native_app))
        with patch.dict(sys.modules, {'AppKit': appkit}), \
                patch('seeutoken.app.sys.platform', 'darwin'), \
                patch('seeutoken.app._run_on_main', lambda fn: fn()), \
                patch('seeutoken.app._ns_window_for', return_value=ns) as lookup:
            app._show_main()
        lookup.assert_called_once_with(app.main_win)
        self.assertEqual(actions.mock_calls, [
            call.window.isMiniaturized(), call.window.deminiaturize_(None),
            call.application.unhide_(None), call.application.activateIgnoringOtherApps_(True),
            call.window.makeKeyAndOrderFront_(None),
        ])

    def test_quit_rejects_queued_navigation_and_sidebar_reveal(self):
        app = self.app()
        app._quitting = True
        app._show_main()
        app._navigate('codex')
        app._set_float_visible(True)
        self.assertEqual(app.main_win.mock_calls, [])
        self.assertEqual(app.float_win.mock_calls, [])

    def test_sidebar_navigation_restores_main_even_if_page_load_fails(self):
        for page, suffix in [('codex', 'dashboard?provider=codex'), ('panels', 'panels')]:
            with self.subTest(page=page):
                app = self.app()
                app._page = lambda name: name
                app._show_main = Mock()
                app.main_win.load_url.side_effect = RuntimeError('temporary navigation failure')
                app._navigate(page)
                app.main_win.load_url.assert_called_once_with(suffix)
                app._show_main.assert_called_once()


class MacDelegateTests(unittest.TestCase):
    def test_dock_reopen_restores_main_even_with_visible_sidebar_and_quit_uses_cleanup(self):
        class DelegateBase:
            @classmethod
            def alloc(cls):
                return cls()

            def init(self):
                return self

        browser = SimpleNamespace(AppDelegate=DelegateBase, app=Mock(), _shared_app_delegate=None)
        cocoa = SimpleNamespace(BrowserView=browser)
        reopen, quit_app = Mock(), Mock()
        with patch.dict(sys.modules, {'webview.platforms.cocoa': cocoa}), \
                patch('seeutoken.mac_lifecycle._delegate_class', None):
            delegate = install_app_delegate(reopen, quit_app)
            self.assertIs(browser._shared_app_delegate, delegate)
            browser.app.setDelegate_.assert_called_once_with(delegate)
            for sidebar_visible in (True, False):
                self.assertFalse(delegate.applicationShouldHandleReopen_hasVisibleWindows_(None, sidebar_visible))
            self.assertEqual(reopen.call_count, 2)
            self.assertEqual(delegate.applicationShouldTerminate_(None), 0)
            quit_app.assert_called_once()


if __name__ == '__main__':
    unittest.main()
