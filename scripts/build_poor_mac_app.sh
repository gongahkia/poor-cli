#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_SRC="$ROOT/apps/PoorMac"
CONFIGURATION="${CONFIGURATION:-release}"
BUILD_DIR="$APP_SRC/.build"
DIST_DIR="$ROOT/dist/macos"
APP_DIR="$DIST_DIR/PoorMac.app"
EXECUTABLE="$BUILD_DIR/$CONFIGURATION/PoorMac"

case "$CONFIGURATION" in
  debug|release) ;;
  *) echo "CONFIGURATION must be debug or release" >&2; exit 2 ;;
esac

swift build --package-path "$APP_SRC" -c "$CONFIGURATION"

rm -rf "$APP_DIR"
mkdir -p "$APP_DIR/Contents/MacOS" "$APP_DIR/Contents/Resources"
cp "$EXECUTABLE" "$APP_DIR/Contents/MacOS/PoorMac"
cp "$APP_SRC/Packaging/Info.plist" "$APP_DIR/Contents/Info.plist"
printf 'APPL????' > "$APP_DIR/Contents/PkgInfo"

if [[ -f "$ROOT/asset/logo/1.png" ]] && command -v sips >/dev/null && command -v iconutil >/dev/null; then
  ICONSET="$DIST_DIR/PoorMac.iconset"
  rm -rf "$ICONSET"
  mkdir -p "$ICONSET"
  for size in 16 32 128 256 512; do
    sips -z "$size" "$size" "$ROOT/asset/logo/1.png" --out "$ICONSET/icon_${size}x${size}.png" >/dev/null
    sips -z "$((size * 2))" "$((size * 2))" "$ROOT/asset/logo/1.png" --out "$ICONSET/icon_${size}x${size}@2x.png" >/dev/null
  done
  iconutil -c icns "$ICONSET" -o "$APP_DIR/Contents/Resources/PoorMac.icns"
  plutil -replace CFBundleIconFile -string PoorMac "$APP_DIR/Contents/Info.plist"
  rm -rf "$ICONSET"
fi

echo "$APP_DIR"
