import ctypes
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from seeutoken.windows_material import apply_material


class WindowsMaterialTests(unittest.TestCase):
    def setUp(self):
        self.form = SimpleNamespace(Handle=SimpleNamespace(ToInt64=lambda: 123), webview=SimpleNamespace())
        self.dwm = Mock()
        self.dwm.DwmSetWindowAttribute.return_value = 0
        self.dwm.DwmExtendFrameIntoClientArea.return_value = 0
        color = SimpleNamespace(Black='black', Transparent='transparent', FromArgb=lambda *rgb: rgb)
        patches = [
            patch.dict(sys.modules, {'System.Drawing': SimpleNamespace(Color=color)}),
            patch('seeutoken.windows_material.transparency_enabled', return_value=True),
            patch('seeutoken.windows_material.sys.getwindowsversion', return_value=SimpleNamespace(build=26200), create=True),
            patch.object(ctypes, 'windll', SimpleNamespace(dwmapi=self.dwm), create=True),
        ]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)

    def test_glass_has_transparent_webview_but_solid_modes_restore_opaque_background(self):
        self.assertEqual(apply_material(self.form, 'liquid-clear')['type'], 'windows-acrylic')
        self.assertEqual(self.form.webview.DefaultBackgroundColor, 'transparent')
        self.assertEqual(apply_material(self.form, 'light')['type'], 'opaque')
        self.assertEqual(self.form.webview.DefaultBackgroundColor, (245, 247, 249))
        self.assertEqual(apply_material(self.form, 'dark')['type'], 'opaque')
        self.assertEqual(self.form.webview.DefaultBackgroundColor, (17, 24, 36))

    def test_windows_accessibility_and_unsupported_dwm_keep_readable_opaque_fallback(self):
        with patch('seeutoken.windows_material.transparency_enabled', return_value=False):
            state = apply_material(self.form, 'liquid-clear')
            self.assertEqual(state['type'], 'opaque')
            self.assertTrue(state['reducedTransparency'])
        self.dwm.DwmSetWindowAttribute.return_value = -1
        state = apply_material(self.form, 'liquid-light-clear')
        self.assertEqual(state['type'], 'opaque')
        self.assertIsNotNone(state['fallbackReason'])
        self.assertNotEqual(self.form.webview.DefaultBackgroundColor, 'transparent')

    def test_geometry_updates_do_not_recreate_the_backdrop(self):
        apply_material(self.form, 'liquid')
        count = self.dwm.DwmSetWindowAttribute.call_count
        apply_material(self.form, 'liquid')
        self.assertEqual(self.dwm.DwmSetWindowAttribute.call_count, count)

    def test_shaped_window_uses_distinct_alpha_and_never_a_rectangular_dwm_backdrop(self):
        self.assertEqual(apply_material(self.form, 'liquid', shaped=True)['type'], 'windows-translucent')
        self.assertEqual(self.form.Opacity, 1.0)
        self.assertEqual(apply_material(self.form, 'liquid-clear', shaped=True)['type'], 'windows-translucent')
        self.assertEqual(self.form.Opacity, .80)
        with patch('seeutoken.windows_material.transparency_enabled', return_value=False):
            self.assertEqual(apply_material(self.form, 'liquid-clear', shaped=True)['type'], 'opaque')
            self.assertEqual(self.form.Opacity, 1.0)
