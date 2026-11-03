import copy
import unittest
from datetime import datetime
from unittest.mock import patch

from seeutoken.api import ApiError, _apply_event_call_counts, _fetch_all_events, clear_heatmap_cache, enrich_usage_details


class CursorCallCountTests(unittest.TestCase):
    def tearDown(self):
        clear_heatmap_cache()

    def event(self, identifier, model='default', timestamp=1000):
        return {'usageEventId': identifier, 'model': model, 'timestamp': timestamp,
                'tokenUsage': {'inputTokens': 10, 'outputTokens': 2}}

    def test_exact_pagination_continues_past_old_twelve_page_limit(self):
        rows = [self.event(str(i)) for i in range(27)]

        def fetch(*args, body, **kwargs):
            offset = (body['page'] - 1) * body['pageSize']
            return {'totalUsageEventsCount': len(rows), 'usageEventsDisplay': rows[offset:offset + body['pageSize']]}

        with patch('seeutoken.api._api_fetch', side_effect=fetch) as api:
            result = _fetch_all_events('test-cookie', 'test-user', 0, 2000,
                                       page_size=2, max_pages=None, require_complete=True)
        self.assertEqual(len(result), 27)
        self.assertEqual(api.call_count, 14)
        self.assertEqual({row['model'] for row in result}, {'auto'})
        # Equal timestamps do not collapse distinct calls.
        self.assertEqual(len({row['id'] for row in result}), 27)

    def test_server_page_size_cap_does_not_truncate_counts(self):
        responses = [{'totalUsageEventsCount': 3, 'usageEventsDisplay': [self.event(str(i))]} for i in range(3)]
        with patch('seeutoken.api._api_fetch', side_effect=responses) as api:
            result = _fetch_all_events('test-cookie', 'test-user', 0, 2000,
                                       max_pages=None, require_complete=True)
        self.assertEqual(len(result), 3)
        self.assertEqual(api.call_count, 3)

    def test_incomplete_duplicate_or_unverifiable_history_is_rejected(self):
        invalid_responses = [
            [{'totalUsageEventsCount': 2, 'usageEventsDisplay': [self.event('one')]},
             {'totalUsageEventsCount': 2, 'usageEventsDisplay': []}],
            [{'totalUsageEventsCount': 2, 'usageEventsDisplay': [self.event('one')]},
             {'totalUsageEventsCount': 2, 'usageEventsDisplay': [self.event('one')]}],
            [{'usageEventsDisplay': [self.event('one')]}],
        ]
        for responses in invalid_responses:
            with self.subTest(responses=responses), patch('seeutoken.api._api_fetch', side_effect=responses):
                with self.assertRaises(ApiError):
                    _fetch_all_events('test-cookie', 'test-user', 0, 2000,
                                      max_pages=None, require_complete=True)

    def test_period_and_model_counts_use_matching_time_ranges(self):
        data = {'periods': {period: {'calls': None, 'tokens': 100} for period in ('today', 'week', 'all')},
                'models': {period: [{'model': 'auto', 'calls': None, 'processedTokens': 100},
                                    {'model': 'explicit', 'calls': 7, 'processedTokens': 20},
                                    {'model': 'unmatched', 'calls': None, 'processedTokens': 50}]
                           for period in ('today', 'week', 'all')}}
        events = [{'time': time, 'model': 'auto'} for time in (0, 10, 20, 30, 40)]
        _apply_event_call_counts(data, events, {'today': 20, 'week': 10, 'all': 0}, 30)
        for period, expected in [('today', 2), ('week', 3), ('all', 4)]:
            self.assertEqual(data['periods'][period]['calls'], expected)
            self.assertEqual(data['models'][period][0]['calls'], expected)
            self.assertEqual(data['models'][period][1]['calls'], 7)
            self.assertIsNone(data['models'][period][2]['calls'])
            self.assertEqual(data['periods'][period]['tokens'], 100)

    def test_enrichment_backfills_counts_without_replacing_recent_detail_rows(self):
        now = datetime.now()
        timestamp = int(now.timestamp() * 1000)
        recent = [{'time': timestamp - 1, 'model': 'auto'}]
        history = [{'time': timestamp - i, 'model': 'auto', 'input': 10, 'output': 2} for i in range(1, 101)]
        template = {'periods': {period: {'calls': None, 'tokens': 1200} for period in ('today', 'week', 'month', 'cycle', 'all')},
                    'models': {period: [{'model': 'auto', 'calls': None, 'processedTokens': 1200}]
                               for period in ('today', 'week', 'month', 'cycle', 'all')},
                    'events': recent, 'quota': {}, 'limits': {}, 'cycle': {}}
        with patch('seeutoken.api._safe_fetch', return_value={}), \
             patch('seeutoken.api._fetch_all_events', return_value=history) as fetch, \
             patch('seeutoken.api._compose_usage_data', side_effect=lambda **kwargs: copy.deepcopy(template)):
            result = enrich_usage_details({'_authCookie': 'test-cookie', 'user': {'id': 'test-user'},
                                           '_cycleStart': timestamp - 10000})
        self.assertEqual(result['periods']['all']['calls'], 100)
        self.assertEqual(result['models']['all'][0]['calls'], 100)
        self.assertEqual(result['events'], recent)
        self.assertTrue(fetch.call_args.kwargs['require_complete'])
        self.assertIsNone(fetch.call_args.kwargs['max_pages'])
        with patch('seeutoken.api._safe_fetch', return_value={}), \
             patch('seeutoken.api._fetch_all_events', side_effect=ApiError('incomplete')), \
             patch('seeutoken.api._compose_usage_data', side_effect=lambda **kwargs: copy.deepcopy(template)):
            failed = enrich_usage_details({'_authCookie': 'test-cookie', 'user': {'id': 'test-user'}})
        self.assertIsNone(failed['models']['all'][0]['calls'])
        self.assertEqual(failed['periods']['all']['tokens'], 1200)


if __name__ == '__main__':
    unittest.main()
