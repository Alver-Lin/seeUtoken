import copy
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from seeutoken.app import SeeUtokenApp
from seeutoken.bridge import AppBridge
from seeutoken.cursor_questions import add_cursor_questions


class CursorQuestionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'state.vscdb'
        with sqlite3.connect(self.path) as conn:
            conn.execute('CREATE TABLE cursorDiskKV (key TEXT PRIMARY KEY, value TEXT)')
            conn.execute('CREATE TABLE ItemTable (key TEXT PRIMARY KEY, value TEXT)')
            conn.execute('INSERT INTO ItemTable VALUES (?, ?)', ('cursorAuth/accessToken', 'PRIVATE TOKEN'))

    def put(self, key, value):
        with sqlite3.connect(self.path) as conn:
            conn.execute('INSERT OR REPLACE INTO cursorDiskKV VALUES (?, ?)', (key, json.dumps(value)))

    def conversation(self, cid='chat', text='第一条问题'):
        self.put('composerData:' + cid, {'fullConversationHeadersOnly': [
            {'bubbleId': 'one', 'type': 1, 'startedAtMs': 1000},
            {'bubbleId': 'assistant', 'type': 2, 'startedAtMs': 2000},
            {'bubbleId': 'two', 'type': 1, 'startedAtMs': 3000},
        ]})
        self.put(f'bubbleId:{cid}:one', {'type': 1, 'text': text, 'context': 'PRIVATE CONTEXT'})
        self.put(f'bubbleId:{cid}:assistant', {'type': 2, 'text': 'PRIVATE ASSISTANT'})
        self.put(f'bubbleId:{cid}:two', {'type': 1, 'text': '第二条问题'})

    def test_matches_question_boundaries_and_conversation_without_changing_usage(self):
        self.conversation()
        self.conversation('other', '另一个会话')
        events = [{'conversationId': cid, 'time': t, 'input': 12, 'output': 8, 'cache': 100, 'tokens': 20}
                  for cid, t in [('chat', 999), ('chat', 1000), ('chat', 2999),
                                 ('chat', 3000), ('other', 2000), ('missing', 3000)]]
        original = copy.deepcopy(events)
        rows = add_cursor_questions(events, self.path)
        self.assertEqual([r['prompt'] for r in rows], ['', '第一条问题', '第一条问题', '第二条问题', '另一个会话', ''])
        self.assertEqual(events, original)
        for event, row in zip(events, rows):
            self.assertEqual({k: v for k, v in row.items() if k != 'prompt'}, event)
        self.assertNotIn('PRIVATE', json.dumps(rows))

    def test_iso_dates_unsorted_headers_and_missing_user_body(self):
        self.put('composerData:chat', {'fullConversationHeadersOnly': [
            {'bubbleId': 'later', 'type': 1, 'createdAt': '2026-10-28T01:01:00Z'},
            {'bubbleId': 'bad', 'type': 1, 'createdAt': 'invalid'},
            {'bubbleId': 'first', 'type': 1, 'createdAt': '2026-10-28T01:00:00Z'},
            {'bubbleId': 'wrong', 'type': 1, 'startedAtMs': 1793149380000},
        ]})
        self.put('bubbleId:chat:first', {'type': 1, 'text': '第一条'})
        self.put('bubbleId:chat:wrong', {'type': 2, 'text': 'PRIVATE ASSISTANT'})
        events = [{'conversationId': 'chat', 'time': t} for t in (1793149200000, 1793149260000, 1793149380000)]
        self.assertEqual([r['prompt'] for r in add_cursor_questions(events, self.path)], ['第一条', '', ''])

    def test_missing_or_invalid_database_does_not_break_detail_rows(self):
        events = [{'conversationId': 'chat', 'time': 3000}]
        self.assertEqual(add_cursor_questions(events, self.path.with_name('missing'))[0]['prompt'], '')
        self.put('composerData:chat', ['invalid composer'])
        self.assertEqual(add_cursor_questions(events, self.path)[0]['prompt'], '')
        with sqlite3.connect(self.path) as conn:
            conn.execute('DROP TABLE cursorDiskKV')
        self.assertEqual(add_cursor_questions(events, self.path)[0]['prompt'], '')

    def test_edited_questions_are_refreshed_and_full_text_is_preserved(self):
        self.conversation()
        events = [{'conversationId': 'chat', 'time': 2000}]
        self.assertEqual(add_cursor_questions(events, self.path)[0]['prompt'], '第一条问题')
        text = '修改后的问题\n' + '长内容' * 1000
        self.put('bubbleId:chat:one', {'type': 1, 'text': text})
        self.assertEqual(add_cursor_questions(events, self.path)[0]['prompt'], text)

    def test_question_text_is_only_added_to_real_detail_payloads(self):
        bridge = AppBridge.__new__(AppBridge)
        bridge.store = SimpleNamespace(get=lambda: {'includeCachedTokens': False})
        payload = {'data': {'events': [{'conversationId': 'chat', 'time': 2000}]}}
        with patch('seeutoken.bridge.add_cursor_questions', return_value=[{'prompt': '用户提问'}]) as reader:
            public = bridge._public_payload(payload)
            reader.assert_not_called()
            self.assertNotIn('prompt', public['data']['events'][0])
            detail = bridge._detail_payload(payload)
            self.assertEqual(detail['data']['events'][0]['prompt'], '用户提问')
            reader.assert_called_once()
            reader.reset_mock()
            bridge._detail_payload({'data': {'demo': True, 'events': [{'time': 2000}]}})
            reader.assert_not_called()

    def test_dashboard_bootstrap_preserves_question_as_text(self):
        root = Path(self.tmp.name)
        (root / 'dashboard').mkdir()
        html = root / 'dashboard' / 'index.html'
        html.write_text('<head><script type="module" src="app.js"></script></head>')
        prompt = '</script><script>window.bad = true</script>'
        detail = {'data': {'events': [{'prompt': prompt}]}}
        app = SeeUtokenApp.__new__(SeeUtokenApp)
        app.bridge = SimpleNamespace(_cached_payload=lambda: detail, _detail_payload=lambda _: detail)
        app.store = SimpleNamespace(get=lambda: {'floatGlassStyle': 'dark'})
        app.main_native = SimpleNamespace(get_state=lambda: {'type': 'opaque'})
        with patch('seeutoken.app.UI', root):
            app._inject_dashboard_bootstrap()
        result = html.read_text()
        self.assertNotIn(prompt, result)
        argument = result.split('window.__seeUtokenLastDetail=JSON.parse(', 1)[1]
        literal, _ = json.JSONDecoder().raw_decode(argument)
        self.assertEqual(json.loads(literal)['data']['events'][0]['prompt'], prompt)


if __name__ == '__main__':
    unittest.main()
