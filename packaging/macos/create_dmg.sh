#!/bin/bash
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
STAGE="$PROJECT_ROOT/build/macos/dmg-stage"
APP="$PROJECT_ROOT/dist/seeUtoken.app"
DMG="$PROJECT_ROOT/dist/seeUtoken-V1.0.1.dmg"
if [ ! -d "$APP" ]; then
  echo "Build dist/seeUtoken.app first." >&2
  exit 1
fi
mkdir -p "$STAGE"
if [ -e "$STAGE/seeUtoken.app" ]; then
  rm -rf "$STAGE/seeUtoken.app"
fi
/usr/bin/ditto "$APP" "$STAGE/seeUtoken.app"
ln -sfn /Applications "$STAGE/Applications"
cp "$PROJECT_ROOT/packaging/macos/INSTALL.txt" "$STAGE/安装说明.txt"
/usr/bin/codesign --verify --deep --strict "$STAGE/seeUtoken.app"
/usr/bin/hdiutil create -volname 'seeUtoken 1.0.1' -srcfolder "$STAGE" -fs HFS+ -format UDZO -imagekey zlib-level=9 -ov "$DMG"
/usr/bin/hdiutil verify "$DMG"
(cd "$PROJECT_ROOT/dist" && /usr/bin/shasum -a 256 seeUtoken-V1.0.1.dmg > seeUtoken-V1.0.1.dmg.sha256)
echo "Created $DMG"
