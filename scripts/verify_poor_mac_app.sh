#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="${APP_DIR:-$ROOT/dist/macos/PoorMac.app}"
INFO_PLIST="$APP_DIR/Contents/Info.plist"
EXECUTABLE="$APP_DIR/Contents/MacOS/PoorMac"

if [[ ! -d "$APP_DIR" ]]; then
  echo "App bundle not found: $APP_DIR" >&2
  exit 2
fi
if [[ ! -x "$EXECUTABLE" ]]; then
  echo "Executable not found or not executable: $EXECUTABLE" >&2
  exit 2
fi

plutil -lint "$INFO_PLIST" >/dev/null

if command -v codesign >/dev/null; then
  codesign --verify --deep --strict --verbose=2 "$APP_DIR"
  codesign -dvv "$APP_DIR"
fi

echo "Verified $APP_DIR"
