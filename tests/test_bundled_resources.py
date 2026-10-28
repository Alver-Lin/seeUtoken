import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from seeutoken.resources import prepare_ui, resource_root


class BundledResourcesTests(unittest.TestCase):
    def test_packaged_ui_is_writable_copy_and_bundle_stays_unchanged(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'ui' / 'panels').mkdir(parents=True)
            source = root / 'ui' / 'panels' / 'index.html'
            source.write_text('<head>bundled UI</head>')
            ui, temporary = prepare_ui(root, frozen=True)
            try:
                self.assertNotEqual(ui, root / 'ui')
                (ui / 'panels' / 'index.html').write_text('private runtime statistics')
                self.assertEqual(source.read_text(), '<head>bundled UI</head>')
            finally:
                temporary.cleanup()
            self.assertFalse(ui.exists())

    def test_source_checkout_keeps_existing_resource_location(self):
        root = Path('/example/source')
        self.assertEqual(prepare_ui(root, frozen=False), (root / 'ui', None))

    def test_frozen_resource_root_uses_pyinstaller_location(self):
        with patch('sys.frozen', True, create=True), patch('sys._MEIPASS', '/example/app/Contents/Frameworks', create=True):
            self.assertEqual(resource_root(), Path('/example/app/Contents/Frameworks'))
