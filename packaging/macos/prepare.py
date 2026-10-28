"""Stage frontend resources and create a macOS icon without user bootstraps."""
from pathlib import Path
import re
import shutil
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / 'build' / 'macos'
BOOTSTRAP = re.compile(r'\s*<script id="seeutoken-(?:bootstrap|dash-bootstrap|float-bootstrap)">[\s\S]*?</script>')


def main():
    destination = BUILD / 'ui'
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(ROOT / 'ui', destination, ignore=shutil.ignore_patterns('.DS_Store', '*.tmp'))
    for page in destination.rglob('*.html'):
        page.write_text(BOOTSTRAP.sub('', page.read_text(encoding='utf-8')), encoding='utf-8')
    with Image.open(ROOT / 'assets' / 'icon.png') as original:
        original.convert('RGBA').resize((1024, 1024), Image.Resampling.LANCZOS).save(BUILD / 'seeUtoken.icns')
    print('Prepared clean UI assets and seeUtoken.icns')


if __name__ == '__main__':
    main()
