"""Create a fixed-location, whole-bundle replacement installer."""
from pathlib import Path
import plistlib
import runpy
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
META = runpy.run_path(str(ROOT / 'packaging' / 'metadata.py'))


def build(app=None, output=None):
    app = Path(app or ROOT / 'build' / 'macos' / 'app' / 'seeUtoken.app')
    output = Path(output or ROOT / 'dist' / f"seeUtoken-V{META['VERSION']}.pkg")
    with (app / 'Contents' / 'Info.plist').open('rb') as stream:
        info = plistlib.load(stream)
    if (info.get('CFBundleIdentifier'), info.get('CFBundleShortVersionString')) != (META['APP_ID'], META['VERSION']):
        raise ValueError('Application identity/version does not match the installer')
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(['/usr/bin/codesign', '--verify', '--deep', '--strict', str(app)], check=True)
    work = ROOT / 'build' / 'macos'
    work.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='pkg-', dir=work) as folder:
        folder = Path(folder)
        payload = folder / 'root'
        payload.mkdir()
        subprocess.run(['/usr/bin/ditto', str(app), str(payload / 'seeUtoken.app')], check=True)
        components = folder / 'components.plist'
        components.write_bytes(plistlib.dumps([{
            'RootRelativeBundlePath': 'seeUtoken.app',
            'BundleIsRelocatable': False,
            'BundleIsVersionChecked': False,  # Also replace rebuilt packages with the same version.
            'BundleHasStrictIdentifier': True,
            'BundleOverwriteAction': 'upgrade',  # Remove obsolete bundle files atomically.
        }]))
        subprocess.run([
            '/usr/bin/pkgbuild', '--root', str(payload), '--component-plist', str(components),
            '--identifier', META['APP_ID'] + '.pkg', '--version', META['VERSION'],
            '--install-location', '/Applications',
            '--scripts', str(ROOT / 'packaging' / 'macos' / 'scripts'), str(output),
        ], check=True)
    return output


if __name__ == '__main__':
    print(build())
