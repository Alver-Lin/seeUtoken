"""Do not leave runnable application bundles behind after producing the installers."""
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
LSREGISTER = '/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister'


def clean(root=ROOT):
    root = Path(root)
    paths = [root / 'build/macos/app/seeUtoken.app', root / 'dist/seeUtoken.app',
             root / 'build/macos/dmg-stage/seeUtoken.app']
    for app in paths:
        if app.is_symlink() or not app.is_dir():
            continue
        with (app / 'Contents/Info.plist').open('rb') as stream:
            info = plistlib.load(stream)
        if info.get('CFBundleIdentifier') != 'com.seeutoken.desktop':
            raise ValueError('Refusing to remove an unrelated build bundle: ' + str(app))
        if sys.platform == 'darwin':
            subprocess.run([LSREGISTER, '-u', str(app)], capture_output=True)
        shutil.rmtree(app)
    if sys.platform == 'darwin':
        # pkgbuild/verification can briefly expose additional temporary bundles.
        # Retire their stale records only within this project's build outputs.
        sys.path.insert(0, str(ROOT))
        from seeutoken.mac_upgrade import registered_apps
        output = subprocess.check_output([LSREGISTER, '-dump'], text=True)
        for path, _ in registered_apps(output):
            generated = any(directory in path.parents for directory in (root / 'build', root / 'dist'))
            if generated and not path.exists():
                subprocess.run([LSREGISTER, '-u', str(path)], capture_output=True)


if __name__ == '__main__':
    clean()
