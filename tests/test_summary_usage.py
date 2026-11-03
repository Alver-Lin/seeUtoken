import copy
import unittest
from unittest.mock import Mock, patch

from seeutoken.bridge import AppBridge
from seeutoken.summary_usage import combine_usage
from seeutoken.api import ApiError, fetch_heatmap_for_year, clear_heatmap_cache


class SummaryUsageTests(unittest.TestCase):
    def source(self, input_tokens, cache, calls=5):
        counts = {'input': input_tokens, 'output': 10, 'cache': cache, 'calls': calls}
        return {'periods': {'all': counts},
                'models': {'all': [{'model': 'shared-model', **counts}]},
                'events': [{'id': 'same-id', 'time': input_tokens, **counts}],
                'heatmap': {'days': {'2026-11-03': counts}}}

    def test_merges_models_days_and_preserves_tool_identity_and_full_totals(self):
        sources = {'cursor': self.source(20, 100), 'codex': self.source(40, 200, 7)}
        original = copy.deepcopy(sources)
        result = combine_usage(sources, 2026)
        self.assertEqual(result['periods']['all']['tokens'], 80)
        self.assertEqual(result['periods']['all']['calls'], 12)
        self.assertEqual(len(result['events']), 2)  # totals must not come from these two rows
        self.assertEqual([row['provider'] for row in result['events']], ['codex', 'cursor'])
        self.assertEqual(len({row['id'] for row in result['events']}), 2)
        self.assertEqual(len(result['models']['all']), 1)
        model = result['models']['all'][0]
        self.assertEqual(model['providers'], ['cursor', 'codex'])
        self.assertEqual(model['tokens'], 80)
        self.assertEqual(model['percent'], 100)
        self.assertEqual(result['heatmap']['tokens'], 80)
        self.assertEqual(result['heatmap']['calls'], 12)
        self.assertEqual(sources, original)

    def test_cache_basis_is_consistent_and_repeatable_and_ignores_demo(self):
        sources = {'codex': self.source(20, 100), 'cursor': {'demo': True, **self.source(900, 900)}}
        for include_cache, tokens in [(True, 130), (False, 30), (True, 130)]:
            result = combine_usage(sources, 2026, include_cache)
            self.assertEqual(result['periods']['all']['tokens'], tokens)
            self.assertEqual(result['models']['all'][0]['tokens'], tokens)
            self.assertEqual(result['events'][0]['tokens'], tokens)
            self.assertEqual(result['heatmap']['tokens'], tokens)

    def test_empty_and_historical_year_and_legacy_heatmap(self):
        self.assertEqual(combine_usage({}, 2025)['heatmap']['tokens'], 0)
        self.assertEqual(len(combine_usage({}, 2025)['heatmap']['months']), 12)
        result = combine_usage({'cursor': {'heatmap': {'days': {
            '2025-12-31': {'tokens': 99, 'calls': 3},
            '2026-01-01': {'input': 10, 'output': 2, 'cache': 50, 'calls': 1}}}}}, 2025, True)
        self.assertEqual(result['heatmap']['tokens'], 99)
        self.assertEqual(result['heatmap']['days']['2026-01-01']['tokens'], 62)

    def test_unknown_calls_are_preserved_for_models_and_combined_totals(self):
        cursor = self.source(20, 100, None)
        codex = self.source(40, 200, 7)
        for sources in ({'cursor': cursor, 'codex': codex}, {'codex': codex, 'cursor': cursor}):
            result = combine_usage(sources, 2026)
            self.assertIsNone(result['periods']['all']['calls'])
            self.assertEqual(result['periods']['all']['knownCalls'], 7)
            self.assertIsNone(result['models']['all'][0]['calls'])
            self.assertEqual(result['models']['all'][0]['knownCalls'], 7)
        unknown = combine_usage({'cursor': cursor}, 2026)
        self.assertIsNone(unknown['models']['all'][0]['calls'])
        self.assertEqual(unknown['models']['all'][0]['knownCalls'], 0)
        zero = combine_usage({'cursor': self.source(0, 0, 0)}, 2026)
        self.assertEqual(zero['models']['all'][0]['calls'], 0)

    def test_bridge_excludes_demo_and_recovers_from_one_provider_failure(self):
        bridge = AppBridge.__new__(AppBridge)
        bridge.store = Mock()
        bridge.store.get.return_value = {'includeCachedTokens': True}
        bridge._cached_payload = Mock(return_value={'data': {'demo': True, **self.source(900, 900)}})
        bridge.get_codex_usage = Mock(return_value={'data': self.source(20, 100)})
        bridge.refresh_usage_background = Mock()
        data = bridge.get_summary_usage(2026)['data']
        self.assertEqual(data['periods']['all']['tokens'], 130)
        self.assertEqual(data['providers'], ['codex'])
        bridge.get_codex_usage.side_effect = RuntimeError('unavailable')
        data = bridge.get_summary_usage(2026)['data']
        self.assertEqual(data['periods']['all']['tokens'], 0)
        self.assertTrue(any('Codex' in notice for notice in data['notices']))
        bridge.refresh_usage_background.assert_not_called()

    def test_real_heatmap_never_uses_demo_cache_or_auth_fallback(self):
        clear_heatmap_cache()
        with patch('seeutoken.api.resolve_session_token', return_value={}), \
             patch('seeutoken.api.get_demo_heatmap') as demo:
            with self.assertRaises(ApiError):
                fetch_heatmap_for_year(2026, allow_demo=False)
            demo.assert_not_called()
        with patch('seeutoken.api._fetch_all_events', return_value=[]) as fetch:
            result = fetch_heatmap_for_year(2026, cookie='test-cookie', user_id='test-user', allow_demo=False)
            self.assertEqual(result['tokens'], 0)
            fetch.assert_called_once()
        clear_heatmap_cache()


if __name__ == '__main__':
    unittest.main()
