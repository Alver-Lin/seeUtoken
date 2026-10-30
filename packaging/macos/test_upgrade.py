"""Verify replacement with the real macOS Installer on a disposable runner only."""
import os
from pathlib import Path
import plistlib
import runpy
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
VERSION = runpy.run_path(str(ROOT / 'packaging' / 'metadata.py'))['VERSION']


def main():
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('Installer integration tests require a disposable GitHub Actions runner')
    app = Path('/Applications/seeUtoken.app')
    if app.exists():
        raise RuntimeError('Refusing to touch an existing application on this runner')
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
        data = Path.home() / '.config/seeUtoken'
        data.mkdir(parents=True, exist_ok=True)
        settings = data / 'settings.json'
        settings.write_text('{"upgrade-test":"preserve"}')
        before = settings.read_bytes()
        process = subprocess.Popen([str(app / 'Contents/MacOS/seeUtoken')])
        package = ROOT / 'dist' / f'seeUtoken-V{VERSION}.pkg'
        try:
            for _ in range(2):
                subprocess.run(['sudo', 'installer', '-pkg', str(package), '-target', '/'], check=True)
                process.wait(timeout=10)
                info = plistlib.loads((app / 'Contents/Info.plist').read_bytes())
                assert info['CFBundleShortVersionString'] == VERSION
                assert not (app / 'Contents/old-version-only.txt').exists()
                assert settings.read_bytes() == before
                subprocess.run(['codesign', '--verify', '--deep', '--strict', str(app)], check=True)
                subprocess.run(['sudo', 'touch', str(app / 'Contents/old-version-only.txt')], check=True)
            print('PASS: running 1.0.1 -> 1.0.2, whole-bundle replacement, same-version reinstall, user data')
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
            subprocess.run(['sudo', 'rm', '-rf', str(app)], check=True)


if __name__ == '__main__':
    main()
