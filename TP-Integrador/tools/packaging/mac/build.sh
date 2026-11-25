#!/bin/bash
# Builds dist-mac/FutbolDeCabeza.app and FutbolDeCabeza-mac-arm64.zip (on a Mac).
# Usage: tools/packaging/mac/build.sh [python-with-pyinstaller]   (default: python3)
set -euo pipefail
PY="${1:-python3}"
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
OUT="$ROOT/dist-mac"
# .icns desde el set de PNG del logo (iconutil viene con macOS, no se instala).
ICONSET="$ROOT/assets/icono/mac/FutbolDeCabeza.iconset"
if [ -d "$ICONSET" ]; then
  iconutil -c icns "$ICONSET" -o "$ROOT/tools/packaging/mac/FutbolDeCabeza.icns"
fi
"$PY" -m PyInstaller --noconfirm --clean --distpath "$OUT" \
  --workpath "$ROOT/build/mac" "$ROOT/tools/packaging/mac/FutbolDeCabeza.spec"
# servidor.txt goes next to the executable (see fdc/online/endpoint.py).
cp "$ROOT/tools/servidor.txt.example" "$OUT/FutbolDeCabeza.app/Contents/MacOS/servidor.txt"
# Re-sign ad hoc after touching the bundle (no developer account: not notarized).
codesign --force --deep --sign - "$OUT/FutbolDeCabeza.app"
cd "$OUT"
ditto -c -k --keepParent FutbolDeCabeza.app FutbolDeCabeza-mac-arm64.zip
shasum -a 256 FutbolDeCabeza-mac-arm64.zip
