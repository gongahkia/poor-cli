#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VERSION="$(awk -F ' = ' '/^version = / { gsub(/"/, "", $2); print $2; exit }' "$ROOT_DIR/Cargo.toml")"
ARCH="${ARCH:-amd64}"
PACKAGE_NAME="walk_${VERSION}_${ARCH}"
OUTPUT_DIR="${1:-"$ROOT_DIR/dist/linux"}"
STAGE_DIR="$(mktemp -d)"
PACKAGE_DIR="$STAGE_DIR/$PACKAGE_NAME"

cleanup() {
    rm -rf "$STAGE_DIR"
}
trap cleanup EXIT

if ! command -v dpkg-deb >/dev/null 2>&1; then
    printf 'dpkg-deb is required to build a .deb package\n' >&2
    exit 1
fi

cargo build --release -p walk --manifest-path "$ROOT_DIR/Cargo.toml"

mkdir -p \
    "$PACKAGE_DIR/DEBIAN" \
    "$PACKAGE_DIR/usr/bin" \
    "$PACKAGE_DIR/usr/share/applications" \
    "$PACKAGE_DIR/usr/share/icons/hicolor/256x256/apps" \
    "$PACKAGE_DIR/usr/share/man/man1"

cp "$ROOT_DIR/target/release/walk" "$PACKAGE_DIR/usr/bin/walk"
cp "$ROOT_DIR/packaging/linux/walk.desktop" \
    "$PACKAGE_DIR/usr/share/applications/walk.desktop"

python3 - "$PACKAGE_DIR/usr/share/icons/hicolor/256x256/apps/walk.png" <<'PY'
import base64
import sys

data = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4////fwAJ+wP9KobjigAAAABJRU5ErkJggg=="
with open(sys.argv[1], "wb") as handle:
    handle.write(base64.b64decode(data))
PY

python3 - "$PACKAGE_DIR/usr/share/man/man1/walk.1.gz" <<'PY'
import gzip
import sys

content = """.TH WALK 1 "Walk"
.SH NAME
walk \\- GPU-accelerated local-first workspace terminal
"""
with gzip.open(sys.argv[1], "wb", compresslevel=9, mtime=0) as handle:
    handle.write(content.encode("utf-8"))
PY

cat > "$PACKAGE_DIR/DEBIAN/control" <<EOF
Package: walk
Version: $VERSION
Section: utils
Priority: optional
Architecture: $ARCH
Maintainer: Walk Contributors
Description: GPU-accelerated local-first workspace terminal
EOF

mkdir -p "$OUTPUT_DIR"
dpkg-deb --build "$PACKAGE_DIR" "$OUTPUT_DIR/$PACKAGE_NAME.deb" >/dev/null
printf 'Built %s\n' "$OUTPUT_DIR/$PACKAGE_NAME.deb"
