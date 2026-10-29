import json
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from PIL import Image
from seeutoken.codex_usage import codex_command
from seeutoken.float_native_material import FloatNativeMaterialController
from seeutoken.process_utils import background_process_options
from seeutoken.windows_float import apply_sidebar


class WindowsCodexTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.platform = patch('seeutoken.codex_usage.sys.platform', 'win32')
        self.platform.start()
        self.addCleanup(self.platform.stop)
        environment = patch.dict('os.environ', {'APPDATA': str(self.root), 'SEEU_CODEX_EXECUTABLE': ''})
        environment.start()
        self.addCleanup(environment.stop)

    def test_native_exe_is_used_directly(self):
        executable = str(self.root / 'Space & Unicode 中文' / 'codex.exe')
        with patch('seeutoken.codex_usage.shutil.which', return_value=executable):
            self.assertEqual(codex_command(), [executable])

    def test_npm_shim_resolves_native_vendor_exe(self):
        binary = self.root / 'npm' / 'node_modules' / '@openai' / 'codex-win32-x64' / 'vendor' / 'x86_64-pc-windows-msvc' / 'codex' / 'codex.exe'
        binary.parent.mkdir(parents=True)
        binary.write_bytes(b'MZ')
        other_arch = self.root / 'npm' / 'node_modules' / '@openai' / 'codex-win32-arm64' / 'vendor' / 'aarch64-pc-windows-msvc' / 'codex' / 'codex.exe'
        other_arch.parent.mkdir(parents=True)
        other_arch.write_bytes(b'MZ')
        with patch('seeutoken.codex_usage.shutil.which', return_value=str(self.root / 'npm' / 'codex.cmd')):
            self.assertEqual(codex_command(), [str(binary)])

    def test_npm_js_fallback_passes_arguments_without_a_shell(self):
        prefix = self.root / 'Space & Unicode 中文'
        entry = prefix / 'node_modules' / '@openai' / 'codex' / 'bin' / 'codex.js'
        entry.parent.mkdir(parents=True)
        entry.write_text('// launcher')
        node = str(prefix / 'node.exe')
        with patch('seeutoken.codex_usage.shutil.which', side_effect=lambda name: node if name == 'node' else str(prefix / 'codex.cmd')):
            self.assertEqual(codex_command(), [node, str(entry)])

    def test_background_process_does_not_flash_a_console(self):
        with patch.object(subprocess, 'CREATE_NO_WINDOW', 0x08000000, create=True):
            self.assertEqual(background_process_options(), {'creationflags': 0x08000000})


class WindowsSidebarTests(unittest.TestCase):
    def test_outline_scales_with_dpi_and_disposes_previous_region(self):
        path, matrix, previous = Mock(), Mock(), Mock()
        region = Mock(return_value='new-region')
        form = SimpleNamespace(InvokeRequired=False, webview=SimpleNamespace(),
                               ClientSize=SimpleNamespace(Width=600, Height=400), Region=previous)
        modules = {
            'System': SimpleNamespace(Action=lambda fn: fn),
            'System.Drawing': SimpleNamespace(Color=SimpleNamespace(FromArgb=lambda *rgb: rgb),
                                               PointF=lambda x, y: (x, y), Region=region),
            'System.Drawing.Drawing2D': SimpleNamespace(FillMode=SimpleNamespace(Winding=1),
                                                      GraphicsPath=lambda _: path, Matrix=lambda: matrix),
        }
        shape = {'width': 300, 'height': 200,
                 'commands': [['M', 10, 10], ['L', 40, 10], ['C', 50, 10, 50, 30, 40, 30], ['Z']]}
        with patch.dict(sys.modules, modules):
            apply_sidebar(SimpleNamespace(native=form), 'liquid-light-clear', shape)
        matrix.Scale.assert_called_once_with(2, 2)
        path.AddLine.assert_called_once_with((10, 10), (40, 10))
        path.AddBezier.assert_called_once_with((40, 10), (50, 10), (50, 30), (40, 30))
        self.assertEqual(form.Region, 'new-region')
        self.assertEqual(form.webview.DefaultBackgroundColor, (248, 251, 255))
        previous.Dispose.assert_called_once()
        path.Dispose.assert_called_once()

    def test_windows_waits_for_outline_before_revealing_opaque_sidebar(self):
        ready = Mock()
        controller = FloatNativeMaterialController(on_ready=ready)
        window = Mock()
        controller.attach(window)
        with patch('seeutoken.float_native_material.sys.platform', 'win32'), patch('seeutoken.windows_float.apply_sidebar') as apply:
            controller.sync({'floatGlassStyle': 'liquid-light-clear'})
            self.assertEqual(controller.get_state()['type'], 'opaque')
            ready.assert_not_called()
            controller.update_shape({'width': 400, 'height': 400, 'commands': [['M', 0, 0], ['L', 66, 0], ['Z']]})
            self.assertEqual(apply.call_args.args[0:2], (window, 'liquid-light-clear'))
            ready.assert_called_once()


class WindowsPackagingTests(unittest.TestCase):
    def test_staging_strips_private_bootstraps_and_generates_windows_icon(self):
        prepare = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'packaging' / 'windows' / 'prepare.py'))['prepare']
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'assets').mkdir()
            for name in ('icon.png', 'tray.png'):
                Image.new('RGBA', (256, 256), 'white').save(root / 'assets' / name)
            original = '<head>' + ''.join(f'<script id="seeutoken-{kind}">{json.dumps({"private": "SECRET"})}</script>'
                                          for kind in ('bootstrap', 'dash-bootstrap', 'float-bootstrap')) + '<script type="module" src="app.js"></script></head>'
            for page in ('panels', 'dashboard', 'float'):
                directory = root / 'ui' / page
                directory.mkdir(parents=True)
                (directory / 'index.html').write_text(original, encoding='utf-8')
            build = root / 'stage'
            prepare(root, build)
            for page in ('panels', 'dashboard', 'float'):
                staged = (build / 'ui' / page / 'index.html').read_text(encoding='utf-8')
                self.assertNotIn('SECRET', staged)
                self.assertIn('type="module"', staged)
                self.assertEqual((root / 'ui' / page / 'index.html').read_text(encoding='utf-8'), original)
            with Image.open(build / 'assets' / 'icon.ico') as icon:
                self.assertIn((256, 256), icon.ico.sizes())
                self.assertIn((16, 16), icon.ico.sizes())


if __name__ == '__main__':
    unittest.main()
