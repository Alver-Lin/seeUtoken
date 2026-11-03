import copy
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from seeutoken.bridge import AppBridge
from seeutoken.heatmap import build_year_grid, recent_daily_usage
from seeutoken.storage import SettingsStore, save_usage_cache, load_usage_cache
from seeutoken.token_accounting import project_usage


class WeeklyUsageTests(unittest.TestCase):
    def test_daily_window_spans_years_and_retains_canonical_counters(self):
        counts = {'input': 20, 'output': 10, 'cache': 100, 'tokens': 30, 'calls': 1}
        rows = recent_daily_usage({'2025-12-27': counts}, datetime(2026, 1, 2))
        self.assertEqual([row['date'] for row in rows],
                         ['2025-12-27', '2025-12-28', '2025-12-29', '2025-12-30',
                          '2025-12-31', '2026-01-01', '2026-01-02'])
        self.assertEqual(rows[0]['cache'], 100)
        self.assertEqual(rows[1]['tokens'], 0)

    def test_card_and_disk_cache_keep_small_daily_series_in_both_token_bases(self):
        with tempfile.TemporaryDirectory() as folder, \
             patch('seeutoken.storage.settings_path', return_value=Path(folder) / 'settings.json'):
            store = SettingsStore()
            bridge = AppBridge(store)
            today = datetime.now().strftime('%Y-%m-%d')
            raw = {'data': {'heatmap': build_year_grid(datetime.now().year, {
                today: {'input': 20, 'output': 10, 'cache': 100, 'tokens': 30, 'calls': 1}})}}
            original = copy.deepcopy(raw)
            for included, expected in [(False, 30), (True, 130), (False, 30)]:
                store.save({'includeCachedTokens': included})
                public = bridge._public_payload(raw)
                card = bridge._card_payload(raw)
                self.assertNotIn('heatmap', card['data'])
                self.assertEqual(len(card['data']['dailyUsage']), 7)
                self.assertEqual(card['data']['dailyUsage'][-1]['tokens'], expected)
                save_usage_cache(public)
                saved = load_usage_cache()
                self.assertEqual(saved['data']['dailyUsage'][-1]['cache'], 100)
                self.assertEqual(bridge._card_payload(saved)['data']['dailyUsage'][-1]['tokens'], expected)
            self.assertEqual(raw, original)

    def test_repeated_projection_and_partial_refresh_keep_known_daily_data(self):
        raw = {'dailyUsage': [{'date': '2026-11-02', 'input': 20, 'output': 10, 'cache': 100}]}
        projected = raw
        for included, expected in [(True, 130), (True, 130), (False, 30)]:
            projected = project_usage(projected, included)
            self.assertEqual(projected['dailyUsage'][0]['tokens'], expected)
        bridge = AppBridge.__new__(AppBridge)
        merged = bridge._merge_preserve_details({'partial': True}, projected)
        self.assertEqual(merged['dailyUsage'], projected['dailyUsage'])


if __name__ == '__main__':
    unittest.main()
