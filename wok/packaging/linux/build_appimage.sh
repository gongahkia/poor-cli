#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUTPUT_DIR="${1:-"$ROOT_DIR/dist/linux"}"
APPDIR="$OUTPUT_DIR/Walk.AppDir"

if ! command -v linuxdeploy >/dev/null 2>&1; then
    printf 'linuxdeploy is required to build an AppImage\n' >&2
    exit 1
fi

cargo build --release -p walk --manifest-path "$ROOT_DIR/Cargo.toml"

rm -rf "$APPDIR"
mkdir -p \
    "$APPDIR/usr/bin" \
    "$APPDIR/usr/share/applications" \
    "$APPDIR/usr/share/icons/hicolor/256x256/apps"

cp "$ROOT_DIR/target/release/walk" "$APPDIR/usr/bin/walk"
cp "$ROOT_DIR/packaging/linux/walk.desktop" \
    "$APPDIR/usr/share/applications/walk.desktop"

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
