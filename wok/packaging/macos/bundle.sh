#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APP_NAME="Walk.app"
OUTPUT_DIR="${1:-"$ROOT_DIR/dist/$APP_NAME"}"
TARGET="${2:-${WALK_TARGET:-}}"
BINARY_PATH="$ROOT_DIR/target/release/walk"
PLIST_PATH="$ROOT_DIR/packaging/macos/Info.plist"

BUILD_ARGS=(build --release -p walk --manifest-path "$ROOT_DIR/Cargo.toml")
if [[ -n "$TARGET" ]]; then
    BUILD_ARGS+=(--target "$TARGET")
    BINARY_PATH="$ROOT_DIR/target/$TARGET/release/walk"
fi

if [[ "${WALK_SKIP_BUILD:-0}" != "1" ]]; then
    cargo "${BUILD_ARGS[@]}"
fi

rm -rf "$OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR/Contents/MacOS" "$OUTPUT_DIR/Contents/Resources"

cp "$BINARY_PATH" "$OUTPUT_DIR/Contents/MacOS/walk"
cp "$PLIST_PATH" "$OUTPUT_DIR/Contents/Info.plist"
chmod +x "$OUTPUT_DIR/Contents/MacOS/walk"

if command -v plutil >/dev/null 2>&1; then
    plutil -lint "$OUTPUT_DIR/Contents/Info.plist" >/dev/null
fi

printf 'Bundled %s\n' "$OUTPUT_DIR"
