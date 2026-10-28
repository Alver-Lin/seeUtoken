import json
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime
from pathlib import Path

from seeutoken.codex_usage import CodexUsage, parse_rollout, window_data


class CodexUsageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.path = self.root / 'sessions' / 'one.jsonl'
        self.path.parent.mkdir()
        self.ts = datetime.now().astimezone().isoformat()

    def tearDown(self):
        self.tmp.cleanup()

    def event(self, input_tokens, cached, output, last=None, **extra):
        usage = {'input_tokens': input_tokens, 'cached_input_tokens': cached,
                 'output_tokens': output, 'reasoning_output_tokens': 9}
        return {'type': 'event_msg', 'timestamp': self.ts, 'payload': {
            'type': 'token_count', 'info': {'total_token_usage': usage,
            'last_token_usage': last or usage}, **extra}}

    def write(self, records):
        prefix = [{'type': 'session_meta', 'payload': {'id': 'test-session', 'cwd': '/projects/demo'}},
                  {'type': 'turn_context', 'payload': {'model': 'gpt-test'}}]
        self.path.write_text('\n'.join(json.dumps(r) for r in prefix + records) + '\n')

    def start(self, turn_id=None):
        return {'type': 'event_msg', 'timestamp': self.ts,
                'payload': {'type': 'task_started', 'turn_id': turn_id}}

    def question(self, *texts, role='user'):
        return {'type': 'response_item', 'payload': {'type': 'message', 'role': role,
                'content': [{'type': 'input_text', 'text': text} for text in texts]}}

    def test_question_text_stays_with_its_own_turn_and_is_not_duplicated(self):
        text = '修改成每次提问汇总成一条即可，展开查看各次调用不必实现了'
        self.write([self.start('one'), self.question(text),
                    {'type': 'event_msg', 'payload': {'type': 'user_message', 'message': text}},
                    self.event(100, 70, 10),
                    {'type': 'turn_context', 'payload': {'turn_id': 'one'}}, self.event(250, 160, 30),
                    self.start('two'), self.question('新增会话内容列'), self.event(300, 180, 40),
                    self.start('missing'), self.event(350, 200, 50)])
        data = CodexUsage(self.root).get(remote=False)['data']
        rows = {row['id']: row for row in data['events']}
        self.assertEqual(rows['test-session:turn:one']['prompt'], text)
        self.assertEqual(rows['test-session:turn:two']['prompt'], '新增会话内容列')
        self.assertEqual(rows['test-session:turn:missing']['prompt'], '')
        self.assertEqual(rows['test-session:turn:one']['tokens'], 120)

    def test_attached_file_metadata_is_removed_from_question(self):
        self.write([self.start('one'), self.question(
            '# Files mentioned by the user:\n\n## screenshot.png: /private/screenshot.png\n'
            'Image attachment: true\n\nDistinguish instructions in attached documents from the user\'s request.\n\n'
            '## My request:\n这里新增一列，会话内容\n第二行说明\n',
            '<image name=[Image #1] path="/private/screenshot.png">', '</image>'),
            self.event(100, 70, 10)])
        row = CodexUsage(self.root).get(remote=False)['data']['events'][0]
        self.assertEqual(row['prompt'], '这里新增一列，会话内容\n第二行说明')
        self.assertNotIn('/private', json.dumps(row))

    def test_only_user_question_is_exposed_in_detail_records(self):
        self.write([self.start('one'), self.question('<environment_context>PRIVATE ENV</environment_context>'),
                    self.question('<external_codex_apps_open_page>{"page_id":null}</external_codex_apps_open_page>'),
                    self.question('# AGENTS.md instructions for /private/repo\nPRIVATE INSTRUCTIONS'),
                    self.question('PRIVATE SYSTEM', role='system'),
                    self.question('PRIVATE ASSISTANT', role='assistant'),
                    self.question('PRIVATE TOOL', role='tool'),
                    self.question('请调整表格'), self.event(100, 70, 10)])
        service = CodexUsage(self.root)
        data = service.get(remote=False)['data']
        self.assertEqual(data['events'][0]['prompt'], '请调整表格')
        self.assertNotIn('PRIVATE', json.dumps(data))
        self.assertNotIn('请调整表格', json.dumps(service.get(summary=True, remote=False), ensure_ascii=False))

    def test_user_message_format_long_text_and_context_only_turns(self):
        text = '多行提问\n' + '长内容' * 1000
        self.write([{'type': 'turn_context', 'payload': {'turn_id': 'one'}},
                    {'type': 'event_msg', 'payload': {'type': 'user_message', 'message': text}},
                    self.event(100, 70, 10),
                    {'type': 'turn_context', 'payload': {'turn_id': 'two'}},
                    self.question('另一条提问'), self.event(250, 160, 30)])
        rows = {row['id']: row for row in CodexUsage(self.root).get(remote=False)['data']['events']}
        self.assertEqual(rows['test-session:turn:one']['prompt'], text)
        self.assertEqual(rows['test-session:turn:two']['prompt'], '另一条提问')

    def test_legacy_records_keep_the_current_user_question(self):
        self.write([self.question('第一条'), self.event(100, 70, 10),
                    self.question('第二条'), self.event(250, 160, 30)])
        rows = CodexUsage(self.root).get(remote=False)['data']['events']
        self.assertEqual([row['prompt'] for row in rows], ['第一条', '第二条'])

    def test_questions_aggregate_calls_without_changing_totals_or_call_counts(self):
        self.write([self.start('question-1'), self.event(1000, 700, 80), self.event(1000, 700, 80),
                    {'type': 'turn_context', 'payload': {'turn_id': 'question-1'}},
                    self.event(1400, 1000, 100), self.start('question-2'), self.event(1600, 1100, 120)])
        data = CodexUsage(self.root).get(remote=False)['data']
        rows = {row['id']: row for row in data['events']}
        self.assertEqual(len(rows), 2)  # Same minute, different questions.
        first = rows['test-session:turn:question-1']
        second = rows['test-session:turn:question-2']
        self.assertEqual((first['input'], first['output'], first['cache'], first['processedTokens']),
                         (400, 100, 1000, 1500))
        self.assertEqual((second['input'], second['output'], second['cache']), (100, 20, 100))
        self.assertEqual(data['periods']['all']['calls'], 3)
        self.assertEqual(data['models']['all'][0]['calls'], 3)
        for field in ('input', 'output', 'cache', 'cacheRead', 'cacheWrite', 'tokens', 'processedTokens'):
            self.assertEqual(sum(row[field] for row in rows.values()), data['periods']['all'][field])
        from seeutoken.token_accounting import project_usage
        self.assertEqual(project_usage(data, False)['events'][0]['tokens'], first['input'] + first['output'])
        self.assertEqual(project_usage(data, True)['events'][0]['tokens'], first['processedTokens'])

    def test_turn_context_identifies_questions_and_preserves_model_breakdown(self):
        self.write([{'type': 'turn_context', 'payload': {'turn_id': 'one'}}, self.event(100, 70, 10),
                    {'type': 'turn_context', 'payload': {'turn_id': 'one', 'model': 'gpt-next'}},
                    self.event(250, 160, 30),
                    {'type': 'turn_context', 'payload': {'turn_id': 'two'}}, self.event(300, 180, 40)])
        data = CodexUsage(self.root).get(remote=False)['data']
        rows = {row['id']: row for row in data['events']}
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows['test-session:turn:one']['model'], 'gpt-test / gpt-next')
        self.assertEqual(rows['test-session:turn:one']['tokens'], 120)
        self.assertEqual(rows['test-session:turn:two']['tokens'], 40)
        self.assertEqual({m['model']: m['calls'] for m in data['models']['all']},
                         {'gpt-test': 1, 'gpt-next': 2})

    def test_active_question_updates_same_row_and_archive_copy_does_not_duplicate(self):
        self.write([self.start('one'), self.event(100, 70, 10)])
        archive = self.root / 'archived_sessions'
        archive.mkdir()
        (archive / 'copy.jsonl').write_bytes(self.path.read_bytes())
        service = CodexUsage(self.root)
        first = service.get(remote=False)['data']['events'][0]
        with self.path.open('a') as stream:
            for record in (self.event(250, 160, 30), self.event(250, 160, 30), self.start('empty')):
                stream.write(json.dumps(record) + '\n')
        for source in (service, CodexUsage(self.root)):
            data = source.get(remote=False)['data']
            self.assertEqual(len(data['events']), 1)
            self.assertEqual(data['events'][0]['id'], first['id'])
            self.assertEqual(data['events'][0]['tokens'], 120)
            self.assertEqual(data['periods']['all']['calls'], 2)

    def test_grouping_happens_before_record_limit(self):
        self.write([self.start('long'), *[self.event(n * 100, n * 70, n * 10) for n in range(1, 206)],
                    self.start('next'), self.event(20600, 14420, 2060)])
        data = CodexUsage(self.root).get(remote=False)['data']
        self.assertEqual(len(data['events']), 2)
        self.assertEqual(data['events'][0]['tokens'], 8200)
        self.assertEqual(data['periods']['all']['tokens'], 8240)
        self.assertEqual(data['periods']['all']['calls'], 206)

    def test_question_id_is_scoped_to_session(self):
        self.write([self.start('same-id'), self.event(100, 70, 10)])
        other = self.path.with_name('other.jsonl')
        other.write_text(self.path.read_text().replace('test-session', 'other-session'))
        data = CodexUsage(self.root).get(remote=False)['data']
        self.assertEqual(len(data['events']), 2)
        self.assertEqual(data['sessionCount'], 2)
        self.assertEqual(data['periods']['all']['tokens'], 80)

    def test_starts_without_ids_and_counter_resets_still_separate_questions(self):
        self.write([self.start(), self.event(100, 70, 10), self.event(30, 10, 5),
                    self.event(50, 20, 9),
                    {'type': 'event_msg', 'payload': {'type': 'turn_aborted'}},
                    self.start(), self.event(100, 50, 20)])
        data = CodexUsage(self.root).get(remote=False)['data']
        self.assertEqual(len(data['events']), 2)
        self.assertEqual(sorted(row['tokens'] for row in data['events']), [31, 79])
        self.assertEqual(data['periods']['all']['tokens'], 110)
        self.assertEqual(data['periods']['all']['calls'], 4)

    def test_question_across_midnight_keeps_daily_call_totals(self):
        midnight = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
        first, second = self.event(100, 70, 10), self.event(250, 160, 30)
        first['timestamp'] = int(midnight.timestamp() * 1000) - 1000
        second['timestamp'] = int(midnight.timestamp() * 1000)
        self.write([self.start('overnight'), first, second])
        data = CodexUsage(self.root).get(remote=False)['data']
        self.assertEqual(len(data['events']), 1)
        self.assertEqual(data['events'][0]['time'], second['timestamp'])
        self.assertEqual(data['events'][0]['tokens'], 120)
        self.assertEqual(data['periods']['today']['tokens'], 80)
        self.assertEqual(data['periods']['today']['calls'], 1)
        self.assertEqual(data['periods']['all']['calls'], 2)
        self.assertEqual(data['heatmap']['days'][midnight.date().isoformat()]['tokens'], 80)

    def test_deltas_ignore_repeated_snapshots_and_dont_add_cache_or_reasoning(self):
        self.write([self.event(100, 70, 10), self.event(100, 70, 10), self.event(250, 160, 30)])
        data = CodexUsage(self.root).get(remote=False)['data']
        total = data['periods']['all']
        self.assertEqual((total['input'], total['output'], total['cache'], total['tokens'], total['calls']),
                         (90, 30, 160, 120, 2))
        self.assertEqual(total['processedTokens'], 280)
        self.assertEqual(data['models']['all'][0]['tokens'], 120)
        self.assertEqual(data['models']['all'][0]['processedTokens'], 280)
        self.assertEqual(data['heatmap']['tokens'], 120)
        self.assertEqual(data['events'][0]['project'], 'demo')

    def test_first_cumulative_baseline_is_not_inherited_usage(self):
        self.write([self.event(5000, 4000, 1000, {'input_tokens': 100, 'cached_input_tokens': 50, 'output_tokens': 10})])
        self.assertEqual(sum(e['tokens'] for e in parse_rollout(self.path)['events']), 60)

    def test_cursor_and_codex_share_uncached_basis_in_every_view(self):
        from seeutoken.api import _summarize_agg, _models_from_agg, _normalize_events
        from seeutoken.heatmap import aggregate_days_from_events

        # Same request, different provider schemas. Cache writes and reasoning
        # must not be counted twice, and repeated quota snapshots add no usage.
        event = self.event(1000, 700, 80)
        for field in ('total_token_usage', 'last_token_usage'):
            event['payload']['info'][field]['cache_write_input_tokens'] = 100
        self.write([event, event])
        codex = CodexUsage(self.root).get(remote=False)['data']
        row = {'modelIntent': 'gpt-test', 'inputTokens': 200, 'outputTokens': 80,
               'cacheReadTokens': 700, 'cacheWriteTokens': 100}
        aggregate = {'aggregations': [row]}
        cursor_event = _normalize_events({'events': [{'timestamp': int(datetime.now().timestamp() * 1000),
                                                     'tokenUsage': row}]})[0]
        items = [*codex['periods'].values(), *codex['events'],
                 *(m for rows in codex['models'].values() for m in rows),
                 _summarize_agg(aggregate), *_models_from_agg(aggregate), cursor_event]
        for item in items:
            self.assertEqual((item['input'], item['output'], item['cache'], item['tokens'], item['processedTokens']),
                             (200, 80, 800, 280, 1080))
        self.assertEqual(codex['usageTokens']['today'], 280)
        self.assertEqual(codex['heatmap']['tokens'], 280)
        self.assertEqual(sum(d['tokens'] for d in aggregate_days_from_events([cursor_event]).values()), 280)
        self.assertEqual(codex['periods']['today']['calls'], 1)

    def test_cache_write_deltas_and_invalid_cache_are_bounded(self):
        first, second = self.event(1000, 600, 80), self.event(1400, 850, 100)
        for field in ('total_token_usage', 'last_token_usage'):
            first['payload']['info'][field]['cache_write_input_tokens'] = 100
            second['payload']['info'][field]['cache_write_input_tokens'] = 150
        self.write([first, second])
        total = CodexUsage(self.root).get(remote=False)['data']['periods']['today']
        self.assertEqual((total['input'], total['cacheRead'], total['cacheWrite'], total['tokens']),
                         (400, 850, 150, 500))
        self.assertEqual(total['processedTokens'], 1500)
        bad = self.event(100, 200, 10)
        bad['payload']['info']['last_token_usage']['cache_write_input_tokens'] = 300
        self.write([bad])
        event = parse_rollout(self.path)['events'][0]
        self.assertEqual((event['input'], event['cache'], event['tokens'], event['processedTokens']),
                         (0, 100, 10, 110))

    def test_resets_model_switches_and_partial_lines(self):
        self.write([self.event(100, 70, 10), {'type': 'turn_context', 'payload': {'model': 'gpt-next'}},
                    self.event(30, 10, 5)])
        with self.path.open('a') as f:
            f.write('{"type":"event_msg", "token_count"')
        data = CodexUsage(self.root).get(remote=False)['data']
        self.assertEqual(data['usageTokens']['all'], 65)
        self.assertEqual(data['periods']['all']['processedTokens'], 145)
        self.assertEqual({m['model'] for m in data['models']['all']}, {'gpt-test', 'gpt-next'})

    def test_missing_and_expired_limits_are_unknown(self):
        self.assertIsNone(window_data(None, 'primary', 0, 5000)['remainingPercent'])
        expired = window_data({'used_percent': 20, 'window_minutes': 300, 'resets_at': 1}, 'primary', 100, 5000)
        self.assertTrue(expired['stale'])
        self.assertIsNone(expired['remainingPercent'])
        self.assertEqual(window_data({'usedPercent': 30}, 'primary', 0, 0)['remainingPercent'], 70)

    def test_archive_duplicates_and_incremental_changes(self):
        self.write([self.event(100, 70, 10)])
        archive = self.root / 'archived_sessions'
        archive.mkdir()
        (archive / 'copy.jsonl').write_bytes(self.path.read_bytes())
        service = CodexUsage(self.root)
        self.assertEqual(service.get(remote=False)['data']['usageTokens']['all'], 40)
        with self.path.open('a') as f:
            f.write(json.dumps(self.event(200, 150, 20)) + '\n')
        self.assertEqual(service.get(remote=False)['data']['usageTokens']['all'], 70)
        self.path.unlink()
        self.assertEqual(service.get(remote=False)['data']['usageTokens']['all'], 40)

    def test_internal_review_excluded_and_summary_contains_no_messages(self):
        self.write([self.event(100, 70, 10), {'type': 'turn_context', 'payload': {'model': 'codex-auto-review'}},
                    self.event(200, 150, 20), {'type': 'response_item', 'payload': {'content': 'PRIVATE CONTENT'}}])
        data = CodexUsage(self.root).get(summary=True, remote=False)['data']
        self.assertEqual(data['usageTokens']['all'], 40)
        self.assertNotIn('models', data)
        self.assertNotIn('events', data)
        self.assertNotIn('PRIVATE CONTENT', json.dumps(data))

    def test_current_account_limits_override_older_snapshot(self):
        self.write([self.event(100, 70, 10, rate_limits={'limit_id': 'codex', 'primary': {'used_percent': 30}})])
        service = CodexUsage(self.root)
        service._remote = {'updatedAt': 9999999999999, 'account': {'planType': 'plus'},
                           'limits': {'rateLimitsByLimitId': {'codex': {'primary': {'usedPercent': 15}}}}}
        data = service.get(remote=False)['data']
        self.assertEqual(data['windows'][0]['remainingPercent'], 85)
        self.assertEqual(data['quotaSource'], 'account')
        self.assertEqual(data['user']['plan'], 'plus')

    def test_configured_refresh_interval_and_manual_refresh(self):
        service = CodexUsage(self.root)
        clock = [0.0]
        with patch('seeutoken.codex_usage.time.monotonic', lambda: clock[0]), patch('seeutoken.codex_usage.threading.Thread') as worker:
            service.get(summary=True, auto_refresh_minutes=5)
            self.assertEqual(worker.return_value.start.call_count, 1)
            service._remote_running = False
            clock[0] = 299
            service.get(summary=True, auto_refresh_minutes=5)
            self.assertEqual(worker.return_value.start.call_count, 1)
            clock[0] = 300
            service.get(summary=True, auto_refresh_minutes=5)
            self.assertEqual(worker.return_value.start.call_count, 2)
            service._remote_running = False
            clock[0] = 10000
            service.get(summary=True, auto_refresh_minutes=0)
            self.assertEqual(worker.return_value.start.call_count, 2)
            service.get(summary=True, auto_refresh_minutes=0, refresh=True)
            self.assertEqual(worker.return_value.start.call_count, 3)
            service.get(summary=True, auto_refresh_minutes=0, refresh=True)
            self.assertEqual(worker.return_value.start.call_count, 3)  # no concurrent requests

    def test_default_interval_and_invalid_setting_fallback(self):
        service = CodexUsage(self.root)
        self.assertEqual(service.get(summary=True, remote=False)['data']['autoRefreshMinutes'], 1)
        self.assertEqual(service.get(summary=True, remote=False, auto_refresh_minutes='bad')['data']['autoRefreshMinutes'], 1)
        clock = [0.0]
        with patch('seeutoken.codex_usage.time.monotonic', lambda: clock[0]), patch('seeutoken.codex_usage.threading.Thread') as worker:
            service.get(summary=True)
            service._remote_running = False
            clock[0] = 59
            service.get(summary=True)
            self.assertEqual(worker.return_value.start.call_count, 1)
            clock[0] = 60
            service.get(summary=True)
            self.assertEqual(worker.return_value.start.call_count, 2)

    def test_refresh_setting_is_saved_separately_from_cursor(self):
        from seeutoken.storage import SettingsStore
        with patch('seeutoken.storage.settings_path', lambda: self.root / 'settings.json'):
            store = SettingsStore()
            store.save({'autoRefreshMinutes': 15, 'codexAutoRefreshMinutes': 30})
            restored = SettingsStore().get()
        self.assertEqual(restored['codexAutoRefreshMinutes'], 30)
        self.assertEqual(restored['autoRefreshMinutes'], 15)


if __name__ == '__main__':
    unittest.main()
