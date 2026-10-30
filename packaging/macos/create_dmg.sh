#!/bin/bash
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
STAGE="$PROJECT_ROOT/build/macos/dmg-stage"
SEEU_PYTHON="${SEEU_BUILD_PYTHON:-$PROJECT_ROOT/.venv/bin/python}"
VERSION=$("$SEEU_PYTHON" "$PROJECT_ROOT/packaging/metadata.py")
PKG="$PROJECT_ROOT/dist/seeUtoken-V$VERSION.pkg"
DMG="$PROJECT_ROOT/dist/seeUtoken-V$VERSION.dmg"
if [ ! -f "$PKG" ]; then
  echo "Build the PKG installer first." >&2
  exit 1
fi
rm -rf "$STAGE"
mkdir -p "$STAGE"
cp "$PKG" "$STAGE/安装 seeUtoken.pkg"
cp "$PROJECT_ROOT/packaging/macos/INSTALL.txt" "$STAGE/安装说明.txt"
/usr/bin/hdiutil create -volname "seeUtoken $VERSION" -srcfolder "$STAGE" -fs HFS+ -format UDZO -imagekey zlib-level=9 -ov "$DMG"
/usr/bin/hdiutil verify "$DMG"
(cd "$PROJECT_ROOT/dist" && /usr/bin/shasum -a 256 "seeUtoken-V$VERSION.dmg" > "seeUtoken-V$VERSION.dmg.sha256")
echo "Created $DMG"
