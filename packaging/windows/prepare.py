"""Stage only public application assets, stripping all runtime user bootstraps."""
from pathlib import Path
import re
import shutil
import runpy
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / 'build' / 'windows'
META = runpy.run_path(str(ROOT / 'packaging' / 'metadata.py'))
BOOTSTRAP = re.compile(r'\s*<script id="seeutoken-(?:bootstrap|dash-bootstrap|float-bootstrap)">[\s\S]*?</script>')


def prepare(root=ROOT, build=BUILD):
    ui = build / 'ui'
    if ui.exists():
        shutil.rmtree(ui)
    shutil.copytree(root / 'ui', ui, ignore=shutil.ignore_patterns('.DS_Store', '*.tmp'))
    for page in ui.rglob('*.html'):
        page.write_text(BOOTSTRAP.sub('', page.read_text(encoding='utf-8')), encoding='utf-8')
    assets = build / 'assets'
    assets.mkdir(parents=True, exist_ok=True)
    version_tuple = (*META['VERSION_PARTS'], 0)
    version = META['VERSION']
    (build / 'version_info.txt').write_text(f'''VSVersionInfo(
  ffi=FixedFileInfo(filevers={version_tuple!r}, prodvers={version_tuple!r},
    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[StringFileInfo([StringTable('040904B0', [
    StringStruct('CompanyName', 'seeUtoken'),
    StringStruct('FileDescription', 'seeUtoken AI usage monitor'),
    StringStruct('FileVersion', '{version}'),
    StringStruct('InternalName', 'seeUtoken'),
    StringStruct('OriginalFilename', 'seeUtoken.exe'),
    StringStruct('ProductName', 'seeUtoken'),
    StringStruct('ProductVersion', '{version}')
  ])]), VarFileInfo([VarStruct('Translation', [1033, 1200])])]
)\n''', encoding='utf-8')
    for name in ('icon.png', 'tray.png'):
        shutil.copy2(root / 'assets' / name, assets / name)
    with Image.open(root / 'assets' / 'icon.png') as original:
        original.convert('RGBA').save(assets / 'icon.ico', format='ICO',
            sizes=[(size, size) for size in (16, 24, 32, 48, 64, 128, 256)])
    print('Prepared clean Windows UI and multi-resolution icon')


if __name__ == '__main__':
    prepare()
