import copy
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from seeutoken.bridge import AppBridge
from seeutoken.heatmap import aggregate_days_from_events, build_year_grid
from seeutoken.storage import SettingsStore
from seeutoken.token_accounting import project_usage


class TokenAccountingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for target, value in [('seeutoken.storage.settings_path', Path(self.tmp.name) / 'settings.json'),
                              ('seeutoken.bridge.load_usage_cache', None)]:
            p = patch(target, return_value=value)
            p.start()
            self.addCleanup(p.stop)
        self.store = SettingsStore()
        self.bridge = AppBridge(self.store)
        event = {'id': 'one', 'time': int(datetime.now().timestamp() * 1000),
                 'input': 200, 'output': 80, 'cache': 800, 'tokens': 280, 'cost': 2, 'calls': 1}
        self.raw = {'periods': {'today': dict(event), 'cycle': dict(event)},
                    'models': {'today': [dict(event, model='test', pool='cursor')]},
                    'events': [event], 'quota': {'remainingPercent': 42},
                    'heatmap': build_year_grid(datetime.now().year, aggregate_days_from_events([event]))}
        self.bridge.usage_cache = {'data': self.raw}

    def test_repeated_toggles_update_every_view_without_mutating_counters(self):
        original = copy.deepcopy(self.raw)
        projected = self.raw
        for included, expected in [(False, 280), (True, 1080), (True, 1080), (False, 280), (True, 1080)]:
            projected = project_usage(projected, included)
            self.assertEqual(projected['usageTokens']['today'], expected)
            self.assertEqual(projected['periods']['today']['tokens'], expected)
            self.assertEqual(projected['models']['today'][0]['tokens'], expected)
            self.assertEqual(projected['events'][0]['tokens'], expected)
            self.assertEqual(projected['heatmap']['tokens'], expected)
            self.assertEqual(sum(d['tokens'] for d in projected['heatmap']['days'].values()), expected)
            self.assertEqual(projected['models']['today'][0]['input'], 200)
            self.assertEqual(projected['models']['today'][0]['processedTokens'], 1080)
            self.assertEqual(projected['quota'], original['quota'])
            cells = [cell for m in projected['heatmap']['months'] for w in m['weeks'] for cell in w if cell]
            self.assertEqual(sum(cell['tokens'] for cell in cells), expected)
        self.assertEqual(self.raw, original)

    def test_saved_setting_drives_cursor_card_float_codex_and_restores_after_restart(self):
        self.assertFalse(self.store.get()['includeCachedTokens'])
        for included, expected in [(False, 280), (True, 1080), (False, 280)]:
            self.bridge.set_settings({'includeCachedTokens': included})
            self.assertEqual(SettingsStore().get()['includeCachedTokens'], included)
            self.assertEqual(self.bridge._card_payload(self.bridge.usage_cache)['data']['usageTokens']['today'], expected)
            self.assertEqual(self.bridge._card_payload(self.bridge.usage_cache)['data']['todayPoolTokens']['cursor']['tokens'], expected)
            self.assertEqual(self.bridge.get_usage_tokens()['today'], expected)
            self.assertEqual(self.bridge._detail_payload(self.bridge.usage_cache)['data']['events'][0]['tokens'], expected)
            with patch.object(self.bridge.codex_usage, 'get', return_value={'data': self.raw}):
                codex = self.bridge.get_codex_usage()['data']
            self.assertEqual(codex['usageTokens']['today'], expected)
            self.assertEqual(codex['heatmap']['tokens'], expected)

    def test_partial_empty_data_does_not_overwrite_known_usage_with_zero(self):
        self.store.save({'includeCachedTokens': True})
        partial = {'data': {'partial': True, 'periods': {'today': {'input': 0, 'output': 0, 'cache': 0, 'calls': None}}}}
        card = self.bridge._card_payload(partial)
        self.assertNotIn('usageTokens', card['data'])
        self.assertNotIn('today', self.bridge._public_payload(partial)['data']['usageTokens'])

    def test_cache_only_usage_can_be_counted_or_explicitly_excluded(self):
        self.raw['periods']['today'] = {'input': 0, 'output': 0, 'cache': 800}
        self.assertEqual(self.bridge.get_usage_tokens()['today'], 0)
        self.store.save({'includeCachedTokens': True})
        self.assertEqual(self.bridge.get_usage_tokens()['today'], 800)


if __name__ == '__main__':
    unittest.main()
