import json
from pathlib import Path
import plistlib
import runpy
import tempfile
import unittest
from unittest.mock import Mock, patch

from seeutoken import mac_upgrade as upgrade

ROOT = Path(__file__).resolve().parents[1]


def app(path, version='1.0.3', identifier=upgrade.APP_ID):
    (path / 'Contents').mkdir(parents=True)
    (path / 'Contents/Info.plist').write_bytes(plistlib.dumps({
        'CFBundleIdentifier': identifier, 'CFBundleShortVersionString': version,
    }))
    return path


def record(path, version='1.0.1', identifier=upgrade.APP_ID):
    return f'\n{"-" * 80}\npath:                       {path} (0x1234)\nidentifier:                 {identifier}\nversion:                    {version} (0x1234)\n'


class MacUpgradeTests(unittest.TestCase):
    def test_only_older_installed_copies_are_removed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            installed = root / 'Applications'
            canonical = app(installed / 'seeUtoken.app')
            old = app(installed / 'seeUtoken 1.0.1.app', '1.0.1')
            newer = app(installed / 'seeUtoken Next.app', '1.0.4')
            rebuilt = app(installed / 'seeUtoken Other.app')
            foreign = app(installed / 'seeUtoken Prototype.app', '1.0.0', 'com.example.other')
            backup = app(root / 'backups/seeUtoken.app', '1.0.1')
            link = installed / 'seeUtoken Link.app'
            link.symlink_to(backup)
            with patch.object(upgrade, 'stop_old_apps') as stop:
                self.assertEqual(upgrade.remove_older_installed_copies(installed, canonical), [str(old)])
            stop.assert_called_once_with([old])
            self.assertFalse(old.exists())
            for path in (canonical, newer, rebuilt, foreign, backup, link):
                self.assertTrue(path.exists(), str(path))

    def test_cleanup_handles_trash_missing_mounts_and_build_copies_without_purging_backups(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            home = root / 'home'
            canonical = app(root / 'Applications/seeUtoken.app')
            old = app(home / 'Applications/seeUtoken.app', '1.0.1')
            trashed = app(home / '.Trash/seeUtoken.app', '1.0.1')
            build = app(root / 'project/dist/seeUtoken.app')
            newer = app(root / 'newer/seeUtoken.app', '1.0.4')
            reused = app(root / 'reused/Other.app', identifier='com.example.other')
            missing = root / 'Volumes/seeUtoken 1.0.1/seeUtoken.app'
            private = home / '.config/seeUtoken'
            private.mkdir(parents=True)
            for name in ('settings.json', 'usage_cache.json'):
                (private / name).write_text('{"preserve":true}')
            dump = ''.join(record(p) for p in (canonical, old, trashed, build, missing, newer, reused))
            run = Mock(return_value=Mock(returncode=0))
            with patch.object(upgrade, 'stop_old_apps'), \
                    patch.object(upgrade.subprocess, 'check_output', side_effect=[dump, record(canonical)]), \
                    patch.object(upgrade.subprocess, 'run', run):
                result = upgrade.cleanup_user(canonical, home)
            self.assertTrue(result['complete'])
            self.assertEqual(set(result['unregisteredCopies']), {str(p) for p in (old, trashed, build, missing)})
            self.assertFalse(old.exists())
            self.assertTrue(trashed.exists())
            self.assertTrue(build.exists())
            self.assertTrue(newer.exists())
            self.assertTrue(reused.exists())
            for name in ('settings.json', 'usage_cache.json'):
                self.assertEqual((private / name).read_text(), '{"preserve":true}')
            state = json.loads((private / 'upgrade-state.json').read_text())
            self.assertTrue(state['complete'])
            self.assertEqual(state['version'], '1.0.3')
            self.assertTrue(all(call.args[0][1] in ('-u', '-f') for call in run.call_args_list))

    def test_failed_index_cleanup_does_not_record_false_success(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            canonical = app(root / 'Applications/seeUtoken.app')
            missing = root / 'old/seeUtoken.app'
            dump = record(canonical) + record(missing)
            with patch.object(upgrade.subprocess, 'check_output', return_value=dump), \
                    patch.object(upgrade.subprocess, 'run'):
                with self.assertRaisesRegex(RuntimeError, 'registrations remain'):
                    upgrade.cleanup_user(canonical, root / 'home')
            self.assertFalse((root / 'home/.config/seeUtoken/upgrade-state.json').exists())

    def test_unrelated_registration_mentions_do_not_match(self):
        dump = record('/Applications/Other.app', identifier='com.example.other') + 'comment: com.seeutoken.desktop\n'
        self.assertEqual(upgrade.registered_apps(dump), [])

    def test_first_launch_retries_invalid_or_replaced_install_state(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            canonical = app(root / 'Applications/seeUtoken.app')
            home = root / 'home'
            state = home / '.config/seeUtoken/upgrade-state.json'
            state.parent.mkdir(parents=True)
            state.write_text('[]')
            with patch.object(upgrade.Path, 'home', return_value=home), patch.object(upgrade, 'cleanup_user') as cleanup:
                upgrade.ensure_user_cleanup(canonical)
                cleanup.assert_called_once_with(canonical)
                cleanup.reset_mock()
                complete = {'complete': True, 'version': '1.0.3', 'application': str(canonical),
                            'inode': canonical.stat().st_ino}
                state.write_text(json.dumps(complete))
                upgrade.ensure_user_cleanup(canonical)
                cleanup.assert_not_called()
                complete['inode'] = -1
                state.write_text(json.dumps(complete))
                upgrade.ensure_user_cleanup(canonical)
                cleanup.assert_called_once_with(canonical)


class BuildCleanupTests(unittest.TestCase):
    def test_installer_build_leaves_no_runnable_app_copy(self):
        cleanup = runpy.run_path(str(ROOT / 'packaging/macos/clean_build.py'))['clean']
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            paths = [app(root / p) for p in ('dist/seeUtoken.app', 'build/macos/app/seeUtoken.app',
                                            'build/macos/dmg-stage/seeUtoken.app')]
            backup = app(root / 'backups/seeUtoken.app', '1.0.1')
            (root / 'dist/seeUtoken-V1.0.3.pkg').write_text('installer')
            with patch('subprocess.run'), patch('subprocess.check_output', return_value=''):
                cleanup(root)
            self.assertTrue(all(not p.exists() for p in paths))
            self.assertTrue(backup.exists())
            self.assertTrue((root / 'dist/seeUtoken-V1.0.3.pkg').exists())


if __name__ == '__main__':
    unittest.main()
