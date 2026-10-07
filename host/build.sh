#!/bin/bash
# Build the Margarita Tank menu bar .app bundle with bundled simulator.
# Usage: cd host && ./build.sh [--install]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SIM_DIR="$SCRIPT_DIR/../simulator"
SIM_BINARY="$SIM_DIR/build-static/clawd-tank-sim"
APP_NAME="Margarita Tank.app"
# Bundle name used before the rebrand; removed on --install so two copies of
# the same app (same bundle id) don't linger in /Applications.
LEGACY_APP_NAME="Clawd Tank.app"

# Always rebuild static simulator — cmake handles incremental builds
echo "==> Building static simulator..."
cd "$SIM_DIR"
cmake -B build-static -DSTATIC_SDL2=ON
cmake --build build-static
cd "$SCRIPT_DIR"

# Build .app with py2app
echo "==> Building .app bundle..."
cd "$SCRIPT_DIR"
rm -rf build dist
.venv/bin/python setup.py py2app 2>&1 | tail -3

# Bundle simulator binary
echo "==> Bundling simulator binary..."
cp "$SIM_BINARY" "dist/$APP_NAME/Contents/Resources/clawd-tank-sim"

echo "==> Built: dist/$APP_NAME"

# Install if requested
if [ "${1:-}" = "--install" ]; then
    echo "==> Installing to /Applications..."
    rm -rf "/Applications/$LEGACY_APP_NAME"
    rm -rf "/Applications/$APP_NAME"
    cp -R "dist/$APP_NAME" "/Applications/$APP_NAME"
    echo "==> Installed to /Applications/$APP_NAME"
fi
