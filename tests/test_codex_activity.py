import json
import tempfile
import time
import unittest
from pathlib import Path

from seeutoken.codex_activity import CodexActivity


class CodexActivityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.path = self.root / 'sessions' / 'one.jsonl'
        self.path.parent.mkdir()
        self.probe = CodexActivity(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def append(self, kind, turn='one'):
        with self.path.open('a') as stream:
            stream.write(json.dumps({'type': 'event_msg', 'payload': {'type': kind, 'turn_id': turn}}) + '\n')

    def test_start_complete_and_abort(self):
        self.assertFalse(self.probe.probe()['busy'])
        self.append('task_started')
        self.assertTrue(self.probe.probe()['busy'])
        self.append('task_complete')
        self.assertFalse(self.probe.probe()['busy'])
        self.append('task_started', 'two')
        self.append('turn_aborted', 'two')
        self.assertFalse(self.probe.probe()['busy'])

    def test_late_completion_does_not_stop_new_turn(self):
        self.append('task_started', 'one')
        self.append('task_started', 'two')
        self.append('task_complete', 'one')
        self.assertTrue(self.probe.probe()['busy'])
        self.append('task_complete', 'two')
        self.assertFalse(self.probe.probe()['busy'])

    def test_partial_line_is_retried(self):
        self.append('task_started')
        self.assertTrue(self.probe.probe()['busy'])
        completed = json.dumps({'type': 'event_msg', 'payload': {'type': 'task_complete', 'turn_id': 'one'}})
        with self.path.open('a') as stream:
            stream.write(completed[:30])
        self.assertTrue(self.probe.probe()['busy'])
        with self.path.open('a') as stream:
            stream.write(completed[30:] + '\n')
        self.assertFalse(self.probe.probe()['busy'])

    def test_stale_deleted_and_truncated_logs_stop(self):
        self.append('task_started')
        self.assertTrue(self.probe.probe()['busy'])
        self.assertFalse(self.probe.probe(now=time.time() + 1300)['busy'])
        self.assertTrue(self.probe.probe()['busy'])
        self.path.write_text('')
        self.assertFalse(self.probe.probe()['busy'])
        self.append('task_started')
        self.assertTrue(self.probe.probe()['busy'])
        self.path.unlink()
        self.assertFalse(self.probe.probe()['busy'])

    def test_multiple_sessions_and_internal_review(self):
        self.append('task_started')
        other = self.path.with_name('two.jsonl')
        other.write_bytes(self.path.read_bytes())
        self.assertEqual(self.probe.probe()['activeTasks'], 2)
        with other.open('a') as stream:
            stream.write(json.dumps({'type': 'turn_context', 'payload': {'model': 'codex-auto-review'}}) + '\n')
        self.assertEqual(self.probe.probe()['activeTasks'], 1)
        self.append('task_complete')
        self.assertFalse(self.probe.probe()['busy'])


if __name__ == '__main__':
    unittest.main()
