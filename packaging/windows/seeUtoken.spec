from pathlib import Path

ROOT = Path(SPECPATH).resolve().parents[1]
BUILD = ROOT / 'build' / 'windows'
a = Analysis(
    [str(ROOT / 'packaging' / 'windows' / 'entry.py')],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[(str(BUILD / 'ui'), 'ui'), (str(BUILD / 'assets'), 'assets')],
    hiddenimports=['webview.platforms.winforms', 'webview.platforms.edgechromium',
                   'pystray._win32', 'clr', 'pythonnet'],
    excludes=['tkinter', 'webview.platforms.cocoa', 'webview.platforms.qt',
              'webview.platforms.gtk', 'webview.platforms.cef', 'webview.platforms.android'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name='seeUtoken',
    debug=False, strip=False, upx=False, console=False,
    icon=str(BUILD / 'assets' / 'icon.ico'),
    version=str(BUILD / 'version_info.txt'),
    uac_admin=False,
)
