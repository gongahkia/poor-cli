#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_SRC="$ROOT/apps/PoorMac"
CONFIGURATION="${CONFIGURATION:-release}"
APP_VERSION="${APP_VERSION:-$(cat "$ROOT/VERSION" 2>/dev/null || echo 0.1.0)}"
BUNDLE_ID="${BUNDLE_ID:-dev.poor-cli.PoorMac}"
CODESIGN_IDENTITY="${CODESIGN_IDENTITY:--}"
ENTITLEMENTS_PATH="${ENTITLEMENTS_PATH:-}"
HARDENED_RUNTIME="${HARDENED_RUNTIME:-}"
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
plutil -replace CFBundleIdentifier -string "$BUNDLE_ID" "$APP_DIR/Contents/Info.plist"
plutil -replace CFBundleShortVersionString -string "$APP_VERSION" "$APP_DIR/Contents/Info.plist"
plutil -replace CFBundleVersion -string "${BUILD_NUMBER:-1}" "$APP_DIR/Contents/Info.plist"
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

if command -v codesign >/dev/null; then
  codesign_args=(--force --sign "$CODESIGN_IDENTITY")
  if [[ -n "$ENTITLEMENTS_PATH" ]]; then
    if [[ ! -f "$ENTITLEMENTS_PATH" ]]; then
      echo "ENTITLEMENTS_PATH does not exist: $ENTITLEMENTS_PATH" >&2
      exit 2
    fi
    codesign_args+=(--entitlements "$ENTITLEMENTS_PATH")
  fi
  if [[ "$HARDENED_RUNTIME" == "1" || "$CODESIGN_IDENTITY" != "-" ]]; then
    codesign_args+=(--options runtime)
  fi
  codesign "${codesign_args[@]}" "$APP_DIR" >/dev/null
fi

echo "$APP_DIR"
