import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from seeutoken.app import SeeUtokenApp
from seeutoken.float_native_material import FloatNativeMaterialController


SHAPE = {"commands": [["M", 0, 0], ["L", 66, 0], ["Z"]], "width": 400, "height": 400}


class FloatMaterialStartupTests(unittest.TestCase):
    def setUp(self):
        self.queue = []
        self.events = []
        self.window = object()
        self.glass = Mock()
        self.patches = [
            patch("seeutoken.float_native_material.sys.platform", "darwin"),
            patch("seeutoken.float_native_material._run_on_main", self.queue.append),
            patch("seeutoken.float_native_material._ns_window_for", return_value=self.window),
            patch("seeutoken.float_native_material._fix_webview_transparency"),
            patch("seeutoken.float_native_material._reduce_transparency", return_value=False),
            patch("seeutoken.float_native_material.liquid_glass_supported", return_value=True),
            patch("seeutoken.float_native_material.MacLiquidGlass", return_value=self.glass),
            patch.dict("os.environ", {"SEEU_FLOAT_NATIVE_GLASS": "1"}),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)
        self.controller = FloatNativeMaterialController(on_ready=lambda: self.events.append("ready"))

    def drain(self):
        while self.queue:
            self.queue.pop(0)()

    def sync(self, mode="liquid-clear"):
        self.controller.sync({"floatGlassStyle": mode}, on_complete=lambda: self.events.append(self.controller.get_state()["type"]))

    def test_native_initialization_first_waits_for_shape(self):
        self.sync()
        self.assertEqual(self.events, [])  # AppKit operation is still queued.
        self.drain()
        self.assertEqual(self.events, ["liquid-glass"])
        self.assertFalse(self.glass.update.call_args.kwargs["visible"])
        self.controller.update_shape(SHAPE)
        self.drain()
        self.assertEqual(self.events, ["liquid-glass", "ready"])
        self.assertTrue(self.glass.update.call_args.kwargs["visible"])

    def test_geometry_first_uses_saved_mode_before_ready(self):
        self.controller.update_shape(SHAPE)
        self.drain()
        self.assertEqual(self.events, [])
        self.sync("liquid")
        self.drain()
        self.assertEqual(self.events, ["liquid-glass", "ready"])
        params = self.glass.update.call_args.kwargs
        self.assertEqual(params["style"], "regular")
        self.assertEqual(params["tint_opacity"], 0)
        self.assertIsNotNone(params["shape"])

    def test_unrelated_setting_sync_does_not_recreate_glass(self):
        self.controller.update_shape(SHAPE)
        self.sync()
        self.drain()
        self.controller.sync({"floatGlassStyle": "liquid-clear", "floatX": 120})
        self.drain()
        self.glass.dispose.assert_not_called()
        self.assertEqual(self.events.count("ready"), 1)
        self.assertEqual(self.glass.update.call_args.kwargs["style"], "clear")

    def test_white_glass_uses_light_native_appearance_and_saved_style(self):
        self.controller.update_shape(SHAPE)
        for mode, style, tint in [("liquid-light", "regular", .12), ("liquid-light-clear", "clear", .24)]:
            with self.subTest(mode=mode):
                self.sync(mode)
                self.drain()
                self.assertEqual(self.controller.get_state()["type"], "liquid-glass")
                self.assertEqual(self.controller.get_state()["floatStyle"], mode)
                params = self.glass.update.call_args.kwargs
                self.assertFalse(params["dark"])
                self.assertEqual(params["style"], style)
                self.assertEqual(params["tint_opacity"], tint)
                self.assertEqual(params["shape"], {**SHAPE, "collapsed": False})

    def test_regular_styles_remove_native_glass_and_can_switch_back(self):
        self.controller.update_shape(SHAPE)
        self.sync()
        self.drain()
        for mode in ("light", "dark"):
            with self.subTest(mode=mode):
                self.sync(mode)
                self.drain()
                self.assertIsNone(self.controller._glass)
                self.assertIsNone(self.controller._vibrancy)
                self.assertEqual(self.controller.get_state()["type"], "transparent")
                self.assertEqual(self.controller.get_state()["floatStyle"], mode)
        self.glass.dispose.assert_called_once()
        self.sync("liquid")
        self.drain()
        self.assertEqual(self.controller.get_state()["type"], "liquid-glass")
        self.assertEqual(self.controller.get_state()["floatStyle"], "liquid")
        self.assertEqual(self.events.count("ready"), 1)

    def test_native_failure_still_reveals_css_fallback(self):
        self.controller.update_shape(SHAPE)
        with patch("seeutoken.float_native_material.MacLiquidGlass", side_effect=RuntimeError("unsupported path")):
            self.sync()
            self.drain()
        self.assertEqual(self.events, ["transparent", "ready"])
        self.assertEqual(self.controller.get_state()["fallbackReason"], "unsupported path")

    def test_removed_frosted_style_uses_default_and_respects_reduced_transparency(self):
        for reduced, expected in [(False, "transparent"), (True, "opaque")]:
            with self.subTest(reduced=reduced):
                controller = FloatNativeMaterialController(on_ready=lambda: self.events.append("ready"))
                controller.update_shape(SHAPE)
                with patch("seeutoken.float_native_material._reduce_transparency", return_value=reduced):
                    controller.sync({"floatGlassStyle": "frosted"})
                    self.drain()
                self.assertEqual(controller.get_state()["type"], expected)
                self.assertIsNone(controller._vibrancy)
                self.assertEqual(controller.get_state()["floatStyle"], "light")
                self.assertIsNone(controller._glass)
                self.assertTrue(controller._ready_notified)

    def test_non_macos_finishes_with_css_material(self):
        with patch("seeutoken.float_native_material.sys.platform", "linux"):
            self.controller.update_shape(SHAPE)
            self.sync()
        self.assertEqual(self.events, ["transparent", "ready"])


class FloatWindowStartupTests(unittest.TestCase):
    def app(self, show=True):
        app = SeeUtokenApp.__new__(SeeUtokenApp)
        app._quitting = False
        app._float_ready = False
        app.float_win = Mock()
        app.float_dock = Mock()
        app.float_native = Mock()
        app.store = SimpleNamespace(get=lambda: {"showFloat": show})
        return app

    def test_show_waits_for_webview_material_classes(self):
        app = self.app()
        app._set_float_visible(True)
        app.float_win.show.assert_not_called()
        app._show_prepared_float()
        app.float_win.show.assert_not_called()
        applied = app.float_native.push_to_webview.call_args.kwargs["on_applied"]
        applied()
        app.float_win.show.assert_called_once()
        app.float_dock.set_visible.assert_called_with(True)

    def test_saved_hidden_preference_is_respected(self):
        app = self.app(show=False)
        app._show_prepared_float()
        app.float_native.push_to_webview.call_args.kwargs["on_applied"]()
        app.float_win.show.assert_not_called()
        app.float_dock.set_visible.assert_called_with(False)

    def test_settings_sync_updates_native_behavior_and_material(self):
        app = self.app()
        settings = {'floatAlwaysOnTop': False, 'floatAutoHide': False}
        with patch('seeutoken.app.sys.platform', 'darwin'):
            app._sync_float_native_material(settings)
        app.float_dock.sync.assert_called_once_with(settings)
        self.assertEqual(app.float_native.sync.call_args.args[0], settings)

    @patch('seeutoken.windows_float.set_topmost')
    def test_panel_changes_push_only_float_settings_and_hide_empty_rail(self, _topmost):
        app = self.app()
        app._float_ready = True
        settings = {'showFloat': True, 'panels': [{'type': 'codex'}, {'type': 'cursor'}],
                    'manualToken': 'PRIVATE', 'floatGlassStyle': 'dark'}
        app.store = SimpleNamespace(get=lambda: settings)
        app._sync_float_native_material(settings)
        script = app.float_win.evaluate_js.call_args.args[0]
        self.assertIn('__seeUtokenApplyFloatSettings', script)
        payload = json.loads(script.split('=', 1)[1].split(';', 1)[0])
        self.assertEqual(payload['panels'], [{'type': 'codex'}, {'type': 'cursor'}])
        self.assertNotIn('PRIVATE', script)
        self.assertEqual(app._float_panel_type_count(), 2)
        app.float_dock.set_visible.assert_called_with(True)
        settings['panels'] = []
        app._sync_float_native_material(settings)
        self.assertEqual(app._float_panel_type_count(), 0)
        app.float_dock.set_visible.assert_called_with(False)
        settings['panels'] = [{'type': 'qoder'}, {'type': 'qoder'}]
        app._sync_float_native_material(settings)
        self.assertEqual(app._float_panel_type_count(), 1)
        app.float_dock.set_visible.assert_called_with(True)

    def test_deleting_all_panels_survives_settings_reload(self):
        from seeutoken.storage import SettingsStore
        with tempfile.TemporaryDirectory() as tmp, patch('seeutoken.storage.settings_path', lambda: Path(tmp) / 'settings.json'):
            store = SettingsStore()
            self.assertEqual(len(store.get()['panels']), 3)
            store.save({'panels': []})
            self.assertEqual(SettingsStore().get()['panels'], [])

    def test_windows_queues_topmost_on_the_ui_thread(self):
        app = self.app()
        with patch('seeutoken.app.sys.platform', 'win32'), \
                patch('seeutoken.windows_float.set_topmost') as topmost:
            app._sync_float_native_material({'floatAlwaysOnTop': False})
            topmost.assert_called_with(app.float_win, False)
            app._sync_float_native_material({'floatAlwaysOnTop': True})
            topmost.assert_called_with(app.float_win, True)

    def test_linux_uses_pywebview_topmost_setting(self):
        app = self.app()
        with patch('seeutoken.app.sys.platform', 'linux'):
            app._sync_float_native_material({'floatAlwaysOnTop': False})
        self.assertFalse(app.float_win.on_top)

    def test_bootstrap_contains_saved_appearance_before_module(self):
        for mode in ("light", "dark", "liquid", "liquid-clear", "liquid-light", "liquid-light-clear"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "float").mkdir()
                html = root / "float" / "index.html"
                html.write_text('<head><script type="module" src="app.js"></script></head>')
                app = self.app()
                app.store = SimpleNamespace(get=lambda: {"floatGlassStyle": mode, "panels": [{"type": "codex"}], "manualToken": "private-value"})
                app.bridge = Mock()
                app.bridge._ensure_card_tokens.return_value = {"data": {}}
                app.float_native.get_state.return_value = {"type": "transparent"}
                with patch("seeutoken.app.UI", root):
                    app._inject_float_bootstrap()
                    app._inject_float_bootstrap()
                text = html.read_text()
                self.assertLess(text.index("__seeUtokenFloatSettings"), text.index('type="module"'))
                self.assertEqual(text.count('id="seeutoken-float-bootstrap"'), 1)
                self.assertIn(mode, text)
                self.assertIn("codex", text)
                self.assertNotIn("manualToken", text)
                self.assertNotIn("private-value", text)


if __name__ == "__main__":
    unittest.main()
