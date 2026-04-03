#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BINARY="${BINARY:-target/release/walk}" # relative to ROOT_DIR
OUTPUT_DIR="${1:-"$ROOT_DIR/dist/linux"}"
APPDIR="$OUTPUT_DIR/Walk.AppDir"

if ! command -v linuxdeploy >/dev/null 2>&1; then
    printf 'linuxdeploy is required to build an AppImage\n' >&2
    exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then # needed for placeholder icon gen
    printf 'python3 is required\n' >&2
    exit 1
fi

if [[ "${WALK_SKIP_BUILD:-0}" != "1" ]]; then
    cargo build --release -p walk --manifest-path "$ROOT_DIR/Cargo.toml"
fi

BINARY_ABS="$ROOT_DIR/$BINARY"
if [ ! -f "$BINARY_ABS" ]; then
    printf "Error: Binary not found at %s. Run 'cargo build --release -p walk' first.\n" "$BINARY_ABS" >&2
    exit 1
fi

rm -rf "$APPDIR"
mkdir -p \
    "$APPDIR/usr/bin" \
    "$APPDIR/usr/share/applications" \
    "$APPDIR/usr/share/icons/hicolor/256x256/apps"

cp "$BINARY_ABS" "$APPDIR/usr/bin/walk"
cp "$ROOT_DIR/packaging/linux/walk.desktop" \
    "$APPDIR/usr/share/applications/walk.desktop"

# include shell integration scripts
if [ -d "$ROOT_DIR/shell-integration" ]; then
    mkdir -p "$APPDIR/usr/share/walk/shell-integration"
    cp "$ROOT_DIR/shell-integration"/* "$APPDIR/usr/share/walk/shell-integration/"
fi

python3 - "$APPDIR/usr/share/icons/hicolor/256x256/apps/walk.png" "$APPDIR/walk.png" <<'PY'
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
