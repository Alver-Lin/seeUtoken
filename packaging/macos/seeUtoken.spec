# Build from the repository root after preparing build/macos/ui and the .icns.
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parents[1]
a = Analysis(
    [str(ROOT / 'packaging' / 'macos' / 'entry.py')],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[(str(ROOT / 'build' / 'macos' / 'ui'), 'ui'), (str(ROOT / 'assets'), 'assets')],
    hiddenimports=['webview.platforms.cocoa', 'pystray._darwin', 'UniformTypeIdentifiers',
                   'WebKit', 'Security', 'Quartz.QuartzCore', 'Quartz.CoreGraphics'],
    excludes=['tkinter', 'webview.platforms.qt', 'webview.platforms.gtk',
              'webview.platforms.winforms', 'webview.platforms.edgechromium',
              'webview.platforms.cef', 'webview.platforms.android'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name='seeUtoken',
    debug=False, strip=False, upx=False, console=False,
    target_arch='arm64', codesign_identity=None, entitlements_file=None,
)
collection = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='seeUtoken')
app = BUNDLE(
    collection, name='seeUtoken.app',
    icon=str(ROOT / 'build' / 'macos' / 'seeUtoken.icns'),
    bundle_identifier='com.seeutoken.desktop', version='1.0.0',
    info_plist={
        'CFBundleDisplayName': 'seeUtoken',
        'CFBundleShortVersionString': '1.0.0',
        'CFBundleVersion': '1.0.0',
        'LSMinimumSystemVersion': '14.0',
        'LSApplicationCategoryType': 'public.app-category.utilities',
        'NSHighResolutionCapable': True,
        'NSRequiresAquaSystemAppearance': False,
        'NSAppTransportSecurity': {'NSAllowsLocalNetworking': True},
    },
)
