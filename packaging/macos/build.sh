#!/bin/bash
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SEEU_PYTHON="${SEEU_BUILD_PYTHON:-$PROJECT_ROOT/.venv/bin/python}"
SEEU_NODE="${SEEU_BUILD_NODE:-node}"
TOOLS="$PROJECT_ROOT/build/macos/tools"
cd "$PROJECT_ROOT"
if [ ! -f "$TOOLS/PyInstaller/__init__.py" ]; then
  "$SEEU_PYTHON" -m pip install --target "$TOOLS" -r packaging/macos/requirements-build.txt
fi
(cd frontend && "$SEEU_NODE" node_modules/vite/bin/vite.js build)
"$SEEU_PYTHON" packaging/macos/prepare.py
PYINSTALLER_CONFIG_DIR="$PROJECT_ROOT/build/macos/cache" PYTHONPATH="$TOOLS" \
  "$SEEU_PYTHON" -m PyInstaller --noconfirm --clean --distpath dist --workpath build/macos/pyinstaller packaging/macos/seeUtoken.spec
bash packaging/macos/create_dmg.sh
