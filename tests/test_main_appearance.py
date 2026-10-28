import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from seeutoken.app import SeeUtokenApp
from seeutoken.main_native_material import MainNativeMaterialController


class MainMaterialTests(unittest.TestCase):
    def setUp(self):
        self.ns = object()
        self.glass = Mock()
        patches = [
            patch('seeutoken.main_native_material.sys.platform', 'darwin'),
            patch('seeutoken.main_native_material._run_on_main', lambda f: f()),
            patch('seeutoken.main_native_material._ns_window_for', return_value=self.ns),
            patch('seeutoken.main_native_material._fix_webview_transparency'),
            patch('seeutoken.main_native_material._configure_window'),
            patch('seeutoken.main_native_material._reduce_transparency', return_value=False),
            patch('seeutoken.main_native_material.liquid_glass_supported', return_value=True),
            patch('seeutoken.main_native_material.MacLiquidGlass', return_value=self.glass),
        ]
        self.mocks = [p.start() for p in patches]
        for p in patches:
            self.addCleanup(p.stop)
        self.controller = MainNativeMaterialController()
        self.controller.attach(Mock())
        self.controller._ensure_vibrancy = Mock()

    def sync(self, mode):
        done = Mock()
        self.controller.sync({'floatGlassStyle': mode}, on_complete=done)
        done.assert_called_once()
        return self.controller.get_state()

    def test_glass_variants_use_full_window_without_float_shape(self):
        for mode, style, tint in [('liquid', 'regular', 0), ('liquid-clear', 'clear', .35)]:
            with self.subTest(mode=mode):
                self.assertEqual(self.sync(mode)['type'], 'liquid-glass')
                self.glass.update.assert_called_with(dark=True, radius=0, style=style, tint_opacity=tint)
                self.mocks[4].assert_called_with(self.ns, mode, True)
                self.mocks[-1].assert_called_with(self.ns)

    def test_solid_modes_remove_glass_and_restore_opaque_window(self):
        self.sync('liquid-clear')
        for mode in ['dark', 'light']:
            self.assertEqual(self.sync(mode)['type'], 'opaque')
            self.mocks[4].assert_called_with(self.ns, mode, False)
            self.assertIsNone(self.controller._glass)
        self.glass.dispose.assert_called_once()
        self.assertEqual(self.sync('liquid')['type'], 'liquid-glass')

    def test_unrelated_settings_do_not_recreate_material(self):
        self.sync('liquid-clear')
        self.sync('liquid-clear')
        self.mocks[-1].assert_called_once()
        self.glass.dispose.assert_not_called()

    def test_older_macos_and_glass_failure_use_vibrancy(self):
        with patch('seeutoken.main_native_material.liquid_glass_supported', return_value=False):
            self.assertEqual(self.sync('liquid')['type'], 'vibrancy')
        self.controller._ensure_vibrancy.assert_called_with(self.ns)
        with patch('seeutoken.main_native_material.MacLiquidGlass', side_effect=RuntimeError('unavailable')):
            self.assertEqual(self.sync('liquid-clear')['type'], 'vibrancy')
            self.assertEqual(self.controller.get_state()['fallbackReason'], 'unavailable')

    def test_failed_material_and_reduced_transparency_are_opaque(self):
        with patch('seeutoken.main_native_material._reduce_transparency', return_value=True):
            self.assertEqual(self.sync('liquid-clear')['type'], 'opaque')
            self.assertTrue(self.controller.get_state()['reducedTransparency'])
            self.controller._ensure_vibrancy.assert_not_called()
        self.controller._ensure_vibrancy.side_effect = RuntimeError('no material')
        with patch('seeutoken.main_native_material.liquid_glass_supported', return_value=False):
            self.assertEqual(self.sync('liquid')['type'], 'opaque')
        self.mocks[4].assert_called_with(self.ns, 'liquid', False)

    def test_other_platforms_finish_with_opaque_css(self):
        with patch('seeutoken.main_native_material.sys.platform', 'win32'):
            self.assertEqual(self.sync('dark')['type'], 'opaque')
        self.mocks[-1].assert_not_called()


class MainAppearanceIntegrationTests(unittest.TestCase):
    def app(self, mode):
        app = SeeUtokenApp.__new__(SeeUtokenApp)
        app.store = SimpleNamespace(get=lambda: {'floatGlassStyle': mode, 'manualToken': 'secret'})
        app.main_native = Mock()
        app.main_native.get_state.return_value = {'type': 'opaque'}
        app.main_win = Mock()
        app.bridge = Mock()
        app.bridge._cached_payload.return_value = {'data': {}}
        app.bridge._card_payload.return_value = {'data': {}}
        app.bridge._detail_payload.return_value = {'data': {}}
        return app

    def test_both_main_pages_bootstrap_saved_mode_before_modules(self):
        for mode in ['light', 'dark', 'liquid', 'liquid-clear']:
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                app = self.app(mode)
                for page in ['panels', 'dashboard']:
                    (root / page).mkdir()
                    path = root / page / 'index.html'
                    path.write_text('<head><script type="module" src="app.js"></script></head>')
                    inject = getattr(app, f'_inject_{page}_bootstrap')
                    with patch('seeutoken.app.UI', root):
                        inject()
                        inject()
                    html = path.read_text()
                    self.assertLess(html.index('__seeUtokenFloatSettings'), html.index('type="module"'))
                    self.assertEqual(html.count('window.__seeUtokenFloatSettings='), 1)
                    self.assertIn(json.dumps(mode), html)
                    self.assertNotIn('secret', html)

    def test_main_updates_even_when_float_is_hidden(self):
        app = self.app('dark')
        app._sync_float_native_material = Mock()
        app._sync_appearance({'floatGlassStyle': 'dark', 'showFloat': False})
        script = app.main_win.evaluate_js.call_args.args[0]
        self.assertIn('__seeUtokenApplyFloatSettings', script)
        app.main_native.sync.assert_called_once()
        app.main_native.sync.call_args.kwargs['on_complete']()
        app.main_native.push_to_webview.assert_called_once()


if __name__ == '__main__':
    unittest.main()
