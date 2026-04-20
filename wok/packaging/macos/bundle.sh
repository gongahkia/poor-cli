#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APP_NAME="Wok.app"
OUTPUT_DIR="${1:-"$ROOT_DIR/dist/$APP_NAME"}"
TARGET="${2:-${WOK_TARGET:-}}"
BINARY_PATH="$ROOT_DIR/target/release/wok"
PLIST_PATH="$ROOT_DIR/packaging/macos/Info.plist"

if [ ! -f "$PLIST_PATH" ]; then
    printf "Error: Info.plist not found at %s\n" "$PLIST_PATH" >&2
    exit 1
fi

BUILD_ARGS=(build --release -p wok --manifest-path "$ROOT_DIR/Cargo.toml")
if [[ -n "$TARGET" ]]; then
    BUILD_ARGS+=(--target "$TARGET")
    BINARY_PATH="$ROOT_DIR/target/$TARGET/release/wok"
fi

if [[ "${WOK_SKIP_BUILD:-0}" != "1" ]]; then
    cargo "${BUILD_ARGS[@]}"
fi

if [ ! -f "$BINARY_PATH" ]; then
    printf "Error: Binary not found at %s. Run 'cargo build --release -p wok' first.\n" "$BINARY_PATH" >&2
    exit 1
fi

rm -rf "$OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR/Contents/MacOS" "$OUTPUT_DIR/Contents/Resources"

cp "$BINARY_PATH" "$OUTPUT_DIR/Contents/MacOS/wok"
cp "$PLIST_PATH" "$OUTPUT_DIR/Contents/Info.plist"
chmod +x "$OUTPUT_DIR/Contents/MacOS/wok"

# include shell integration scripts
if [ -d "$ROOT_DIR/shell-integration" ]; then
    mkdir -p "$OUTPUT_DIR/Contents/Resources/shell-integration"
    cp "$ROOT_DIR/shell-integration"/* "$OUTPUT_DIR/Contents/Resources/shell-integration/"
fi

if command -v plutil >/dev/null 2>&1; then
    plutil -lint "$OUTPUT_DIR/Contents/Info.plist" >/dev/null
fi

printf 'Bundled %s\n' "$OUTPUT_DIR"
