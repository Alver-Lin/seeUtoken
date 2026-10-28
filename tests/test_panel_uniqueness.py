import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from seeutoken.storage import DEFAULT_PANELS, SettingsStore, normalize_panels


class UniquePanelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'settings.json'
        patcher = patch('seeutoken.storage.settings_path', return_value=self.path)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_existing_duplicates_preserve_first_panel_and_provider_order(self):
        first = {'id': 'first', 'type': 'codex', 'name': 'My Codex', 'createdAt': 123}
        self.path.write_text(json.dumps({'panels': [first, DEFAULT_PANELS[0], {'id': 'duplicate', 'type': 'codex'}]}))
        panels = SettingsStore().get()['panels']
        self.assertEqual(panels, [first, DEFAULT_PANELS[0]])

    def test_save_cannot_persist_duplicate_provider(self):
        store = SettingsStore()
        result = store.save({'panels': [*DEFAULT_PANELS, {'id': 'duplicate', 'type': 'cursor'}]})
        self.assertEqual(len(result['panels']), 3)
        self.assertEqual(len(SettingsStore().get()['panels']), 3)
        self.assertEqual(len(json.loads(self.path.read_text())['panels']), 3)

    def test_legacy_provider_and_type_share_one_identity(self):
        panels = normalize_panels([{'id': 'legacy', 'provider': 'Codex'}, {'id': 'new', 'type': 'codex'}])
        self.assertEqual(len(panels), 1)
        self.assertEqual(panels[0]['id'], 'legacy')
        self.assertEqual(panels[0]['type'], 'codex')

    def test_deleting_provider_allows_readding_it_once(self):
        store = SettingsStore()
        store.save({'panels': [p for p in DEFAULT_PANELS if p['type'] != 'codex']})
        replacement = {'id': 'replacement', 'type': 'codex'}
        store.save({'panels': [replacement, *store.get()['panels'], {'id': 'duplicate', 'type': 'codex'}]})
        codex = [p for p in SettingsStore().get()['panels'] if p['type'] == 'codex']
        self.assertEqual(codex, [replacement])

    def test_empty_panels_stay_empty_and_invalid_entries_are_ignored(self):
        store = SettingsStore()
        store.save({'panels': []})
        self.assertEqual(SettingsStore().get()['panels'], [])
        self.assertEqual(normalize_panels([None, 'cursor', {'id': 'codex', 'type': 'codex'}]), [{'id': 'codex', 'type': 'codex'}])


if __name__ == '__main__':
    unittest.main()
