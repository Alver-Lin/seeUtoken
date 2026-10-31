"""Verify replacement with the real macOS Installer on a disposable runner only."""
import os
from pathlib import Path
import plistlib
import runpy
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
VERSION = runpy.run_path(str(ROOT / 'packaging' / 'metadata.py'))['VERSION']
sys.path.insert(0, str(ROOT))
from seeutoken.mac_upgrade import APP_ID, LSREGISTER, registered_apps


def main():
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('Installer integration tests require a disposable GitHub Actions runner')
    app = Path('/Applications/seeUtoken.app')
    if app.exists():
        raise RuntimeError('Refusing to touch an existing application on this runner')
    assert not (ROOT / 'dist/seeUtoken.app').exists(), 'Build left an extra discoverable .app'
    assert not (ROOT / 'build/macos/app/seeUtoken.app').exists(), 'Build staging .app was not cleaned'
    with tempfile.TemporaryDirectory() as folder:
        folder = Path(folder)
        contents = folder / 'seeUtoken.app' / 'Contents'
        (contents / 'MacOS').mkdir(parents=True)
        (contents / 'Info.plist').write_bytes(plistlib.dumps({
            'CFBundleIdentifier': 'com.seeutoken.desktop', 'CFBundleShortVersionString': '1.0.1',
            'CFBundleExecutable': 'seeUtoken', 'CFBundlePackageType': 'APPL',
        }))
        obsolete = contents / 'old-version-only.txt'
        obsolete.write_text('must disappear during a whole-bundle upgrade')
        source = folder / 'legacy.c'
        source.write_text('#include <unistd.h>\nint main(void) { for (;;) sleep(1); }\n')
        subprocess.run(['cc', str(source), '-o', str(contents / 'MacOS/seeUtoken')], check=True)
        subprocess.run(['sudo', 'ditto', str(contents.parent), str(app)], check=True)
        system_old = Path('/Applications/seeUtoken 1.0.1.app')
        user_old = Path.home() / 'Applications/seeUtoken.app'
        unrelated = Path.home() / 'Applications/seeUtoken-upgrade-unrelated.app'
        assert not system_old.exists() and not user_old.exists() and not unrelated.exists()
        user_old.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(['sudo', 'ditto', str(contents.parent), str(system_old)], check=True)
        shutil.copytree(contents.parent, user_old)
        backup = folder / 'trash-copy/seeUtoken.app'
        shutil.copytree(contents.parent, backup)
        missing = folder / 'old-dmg-copy/seeUtoken.app'
        shutil.copytree(contents.parent, missing)
        shutil.copytree(contents.parent, unrelated)
        other_info = plistlib.loads((unrelated / 'Contents/Info.plist').read_bytes())
        other_info['CFBundleIdentifier'] = 'com.example.unrelated'
        (unrelated / 'Contents/Info.plist').write_bytes(plistlib.dumps(other_info))
        for registered in (app, system_old, user_old, backup, missing, unrelated):
            subprocess.run([LSREGISTER, '-f', str(registered)], check=True)
        shutil.rmtree(missing)
        data = Path.home() / '.config/seeUtoken'
        data.mkdir(parents=True, exist_ok=True)
        settings = data / 'settings.json'
        settings.write_text('{"upgrade-test":"preserve"}')
        before = settings.read_bytes()
        processes = [subprocess.Popen([str(p / 'Contents/MacOS/seeUtoken')])
                     for p in (app, system_old, user_old)]
        package = ROOT / 'dist' / f'seeUtoken-V{VERSION}.pkg'
        try:
            for _ in range(2):
                subprocess.run(['sudo', 'installer', '-pkg', str(package), '-target', '/'], check=True)
                for process in processes:
                    process.wait(timeout=10)
                info = plistlib.loads((app / 'Contents/Info.plist').read_bytes())
                assert info['CFBundleShortVersionString'] == VERSION
                assert not (app / 'Contents/old-version-only.txt').exists()
                assert settings.read_bytes() == before
                console_uid = int(subprocess.check_output(['stat', '-f', '%u', '/dev/console'], text=True))
                if console_uid != os.getuid():
                    # No GUI user at install time: exercise the first-launch fallback.
                    subprocess.run([str(app / 'Contents/MacOS/seeUtoken'), '--complete-upgrade'], check=True)
                state_path = data / 'upgrade-state.json'
                assert state_path.is_file() and state_path.stat().st_uid == os.getuid(), 'Cleanup did not run as the login user'
                assert not system_old.exists() and not user_old.exists(), 'Older installed copy remains'
                assert backup.exists() and unrelated.exists(), 'Unrelated files or recoverable backups were removed'
                registered = registered_apps(subprocess.check_output([LSREGISTER, '-dump'], text=True))
                assert {path for path, _ in registered} == {app}, 'Duplicate seeUtoken registrations remain'
                subprocess.run(['codesign', '--verify', '--deep', '--strict', str(app)], check=True)
                subprocess.run(['sudo', 'touch', str(app / 'Contents/old-version-only.txt')], check=True)
            print(f'PASS: running 1.0.1 -> {VERSION}, old copies removed, user registrations deduplicated, no build copies, same-version reinstall, user data')
        finally:
            for process in processes:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=10)
            for installed in (app, system_old, user_old, unrelated):
                subprocess.run([LSREGISTER, '-u', str(installed)], capture_output=True)
            subprocess.run(['sudo', 'rm', '-rf', str(app), str(system_old)], check=True)
            for installed in (user_old, unrelated):
                if installed.exists():
                    shutil.rmtree(installed)


if __name__ == '__main__':
    main()
