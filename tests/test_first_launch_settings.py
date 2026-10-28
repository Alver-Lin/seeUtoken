import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from seeutoken.app import SeeUtokenApp
from seeutoken.storage import SettingsStore


class FirstLaunchSettingsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'settings.json'
        patcher = patch('seeutoken.storage.settings_path', return_value=self.path)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_new_install_uses_requested_defaults(self):
        settings = SettingsStore().get()
        self.assertFalse(settings['includeCachedTokens'])
        self.assertEqual(settings['floatGlassStyle'], 'light')
        self.assertTrue(settings['showFloat'])
        self.assertTrue(settings['floatAutoHide'])
        self.assertTrue(settings['floatAlwaysOnTop'])
        # The pre-module bootstrap must agree with the settings dialog and float.
        self.assertEqual(SeeUtokenApp._float_settings_payload(settings)['floatGlassStyle'], 'light')
        self.assertEqual(SeeUtokenApp._float_settings_payload({})['floatGlassStyle'], 'light')

    def test_existing_preferences_are_preserved_on_restart(self):
        for mode in ['light', 'dark', 'liquid', 'liquid-clear']:
            with self.subTest(mode=mode):
                preferences = {'includeCachedTokens': True, 'floatGlassStyle': mode,
                               'showFloat': False, 'floatAutoHide': False, 'floatAlwaysOnTop': False}
                SettingsStore().save(preferences)
                loaded = SettingsStore().get()
                self.assertEqual({key: loaded[key] for key in preferences}, preferences)

    def test_old_settings_fill_only_missing_defaults(self):
        self.path.write_text(json.dumps({'showFloat': False, 'floatGlassStyle': 'liquid-clear'}))
        settings = SettingsStore().get()
        self.assertFalse(settings['showFloat'])
        self.assertEqual(settings['floatGlassStyle'], 'liquid-clear')
        self.assertFalse(settings['includeCachedTokens'])
        self.assertTrue(settings['floatAutoHide'])
        self.assertTrue(settings['floatAlwaysOnTop'])


if __name__ == '__main__':
    unittest.main()
