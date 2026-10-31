from pathlib import Path
import plistlib
import runpy
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from seeutoken.windows_upgrade import prepare_upgrade

ROOT = Path(__file__).resolve().parents[1]
IDENTITY = {'ProductName': 'seeUtoken', 'FileDescription': 'seeUtoken AI usage monitor'}


class WindowsUpgradeTests(unittest.TestCase):
    def process(self, pid, exe, username='PC\\Alice'):
        return SimpleNamespace(pid=pid, info={'pid': pid, 'exe': exe, 'username': username})

    def api(self, processes, alive=()):
        current = SimpleNamespace(pid=100, username=lambda: 'PC\\Alice',
                                  parents=lambda: [SimpleNamespace(pid=90), SimpleNamespace(pid=80)])
        return SimpleNamespace(Process=lambda: current, process_iter=lambda _: processes,
                               wait_procs=Mock(return_value=([], list(alive))))

    def test_closes_installed_and_legacy_portable_instances_but_never_installer_or_other_users(self):
        installed = self.process(1, r'C:\Users\Alice\AppData\Local\Programs\seeUtoken\seeUtoken.exe')
        portable = self.process(2, r'C:\Users\Alice\Downloads\seeUtoken-V1.0.1.exe')
        processes = [installed, portable,
                     self.process(100, r'C:\Temp\seeUtoken.exe'),
                     self.process(90, r'C:\Downloads\seeUtoken-V1.0.2.exe'),
                     self.process(80, r'C:\Temp\seeUtoken.exe'),
                     self.process(3, r'C:\Users\Bob\seeUtoken.exe', 'PC\\Bob'),
                     self.process(4, r'C:\Other\seeUtoken.exe'),
                     self.process(5, r'C:\Other\unrelated.exe')]
        identity = lambda exe: {} if '\\Other\\' in exe else IDENTITY
        close = Mock()
        api = self.api(processes)
        self.assertEqual(prepare_upgrade(api, identity, close)['closedProcesses'], 2)
        close.assert_called_once_with({1, 2})
        api.wait_procs.assert_called_once_with([installed, portable], timeout=20)

    def test_failed_graceful_exit_aborts_before_installation(self):
        process = self.process(1, r'C:\Apps\seeUtoken.exe')
        close = Mock()
        with self.assertRaisesRegex(RuntimeError, 'existing installation is unchanged'):
            prepare_upgrade(self.api([process], alive=[process]), lambda _: IDENTITY, close, timeout=1)
        close.assert_called_once_with({1})

    def test_filename_without_product_identity_is_never_closed(self):
        close = Mock()
        api = self.api([self.process(1, r'C:\Apps\seeUtoken.exe')])
        self.assertTrue(prepare_upgrade(api, lambda _: {'ProductName': 'Other app'}, close)['ok'])
        close.assert_not_called()
        api.wait_procs.assert_not_called()


class MacInstallerTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform == 'darwin', 'macOS process preflight integration')
    def test_preinstall_closes_only_validated_installed_executable(self):
        with tempfile.TemporaryDirectory() as folder:
            volume = Path(folder).resolve()
            contents = volume / 'Applications/seeUtoken.app/Contents'
            (contents / 'MacOS').mkdir(parents=True)
            (contents / 'Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier': 'com.seeutoken.desktop'}))
            source = volume / 'wait.c'
            source.write_text('#include <unistd.h>\nint main(void) { for (;;) sleep(1); }\n')
            installed = contents / 'MacOS/seeUtoken'
            subprocess.run(['cc', str(source), '-o', str(installed)], check=True, capture_output=True)
            unrelated = volume / 'unrelated'
            unrelated.write_bytes(installed.read_bytes())
            unrelated.chmod(0o755)
            old = subprocess.Popen([str(installed)])
            other = subprocess.Popen([str(unrelated), str(installed)])
            try:
                subprocess.run(['/bin/sh', str(ROOT / 'packaging/macos/scripts/preinstall'),
                                'test.pkg', '/Applications', str(volume)], check=True, timeout=25)
                self.assertIsNotNone(old.poll())
                self.assertIsNone(other.poll())
            finally:
                for process in (old, other):
                    if process.poll() is None:
                        process.terminate()
                    process.wait(timeout=5)

    def test_package_replaces_whole_bundle_at_fixed_path_and_uses_matching_version(self):
        package = runpy.run_path(str(ROOT / 'packaging' / 'macos' / 'create_pkg.py'))
        meta = package['META']
        with tempfile.TemporaryDirectory() as folder:
            app = Path(folder) / 'seeUtoken.app'
            (app / 'Contents').mkdir(parents=True)
            (app / 'Contents' / 'Info.plist').write_bytes(plistlib.dumps({
                'CFBundleIdentifier': meta['APP_ID'], 'CFBundleShortVersionString': meta['VERSION'],
            }))
            policies = []
            def command(args, **kwargs):
                if args[0] == '/usr/bin/pkgbuild':
                    self.assertTrue(Path(args[-1]).parent.is_dir())
                    policies.extend(plistlib.loads(Path(args[args.index('--component-plist') + 1]).read_bytes()))
                    self.assertEqual(args[args.index('--install-location') + 1], '/Applications')
                    self.assertEqual(args[args.index('--identifier') + 1], 'com.seeutoken.desktop.pkg')
                    self.assertEqual(args[args.index('--version') + 1], meta['VERSION'])
                return SimpleNamespace(returncode=0)
            with patch('subprocess.run', side_effect=command):
                package['build'](app, Path(folder) / 'fresh-dist/test.pkg')
            self.assertEqual(policies, [{
                'RootRelativeBundlePath': 'seeUtoken.app', 'BundleIsRelocatable': False,
                'BundleIsVersionChecked': False, 'BundleHasStrictIdentifier': True,
                'BundleOverwriteAction': 'upgrade',
            }])

    def test_package_refuses_mismatched_application_identity_before_build(self):
        package = runpy.run_path(str(ROOT / 'packaging' / 'macos' / 'create_pkg.py'))
        with tempfile.TemporaryDirectory() as folder:
            app = Path(folder) / 'Other.app'
            (app / 'Contents').mkdir(parents=True)
            (app / 'Contents' / 'Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier': 'other'}))
            with patch('subprocess.run') as run:
                with self.assertRaisesRegex(ValueError, 'identity/version'):
                    package['build'](app)
                run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
