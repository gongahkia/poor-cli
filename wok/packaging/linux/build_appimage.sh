#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BINARY="${BINARY:-target/release/wok}" # relative to ROOT_DIR
OUTPUT_DIR="${1:-"$ROOT_DIR/dist/linux"}"
APPDIR="$OUTPUT_DIR/Wok.AppDir"

if ! command -v linuxdeploy >/dev/null 2>&1; then
    printf 'linuxdeploy is required to build an AppImage\n' >&2
    exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then # needed for placeholder icon gen
    printf 'python3 is required\n' >&2
    exit 1
fi

if [[ "${WOK_SKIP_BUILD:-0}" != "1" ]]; then
    cargo build --release -p wok --manifest-path "$ROOT_DIR/Cargo.toml"
fi

BINARY_ABS="$ROOT_DIR/$BINARY"
if [ ! -f "$BINARY_ABS" ]; then
    printf "Error: Binary not found at %s. Run 'cargo build --release -p wok' first.\n" "$BINARY_ABS" >&2
    exit 1
fi

rm -rf "$APPDIR"
mkdir -p \
    "$APPDIR/usr/bin" \
    "$APPDIR/usr/share/applications" \
    "$APPDIR/usr/share/icons/hicolor/256x256/apps"

cp "$BINARY_ABS" "$APPDIR/usr/bin/wok"
cp "$ROOT_DIR/packaging/linux/wok.desktop" \
    "$APPDIR/usr/share/applications/wok.desktop"

# include shell integration scripts
if [ -d "$ROOT_DIR/shell-integration" ]; then
    mkdir -p "$APPDIR/usr/share/wok/shell-integration"
    cp "$ROOT_DIR/shell-integration"/* "$APPDIR/usr/share/wok/shell-integration/"
fi

python3 - "$APPDIR/usr/share/icons/hicolor/256x256/apps/wok.png" "$APPDIR/wok.png" <<'PY'
import base64
import sys

data = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4////fwAJ+wP9KobjigAAAABJRU5ErkJggg=="
decoded = base64.b64decode(data)
for path in sys.argv[1:]:
    with open(path, "wb") as handle:
        handle.write(decoded)
PY

mkdir -p "$OUTPUT_DIR"
(
    cd "$OUTPUT_DIR"
    linuxdeploy --appdir "$APPDIR" --output appimage >/dev/null
)
printf 'Built AppImage in %s\n' "$OUTPUT_DIR"
