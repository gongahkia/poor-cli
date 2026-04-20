#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VERSION="$(awk -F ' = ' '/^version = / { gsub(/"/, "", $2); print $2; exit }' "$ROOT_DIR/Cargo.toml")"
TARGET="${WOK_TARGET:-}"
ARCH="${ARCH:-}"
PACKAGE_NAME="wok_${VERSION}_${ARCH}"
OUTPUT_DIR="${1:-"$ROOT_DIR/dist/linux"}"
STAGE_DIR="$(mktemp -d)"
PACKAGE_DIR="$STAGE_DIR/$PACKAGE_NAME"
BINARY_PATH="$ROOT_DIR/target/release/wok"

cleanup() {
    rm -rf "$STAGE_DIR"
}
trap cleanup EXIT

if ! command -v dpkg-deb >/dev/null 2>&1; then
    printf 'dpkg-deb is required to build a .deb package\n' >&2
    exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then # needed for icon/man gen
    printf 'python3 is required\n' >&2
    exit 1
fi

BUILD_ARGS=(build --release -p wok --manifest-path "$ROOT_DIR/Cargo.toml")
if [[ -n "$TARGET" ]]; then
    BUILD_ARGS+=(--target "$TARGET")
    BINARY_PATH="$ROOT_DIR/target/$TARGET/release/wok"
    if [[ -z "$ARCH" ]]; then
        case "$TARGET" in
            x86_64-unknown-linux-gnu) ARCH="amd64" ;;
            aarch64-unknown-linux-gnu) ARCH="arm64" ;;
        esac
    fi
    PACKAGE_NAME="wok_${VERSION}_${ARCH}"
    PACKAGE_DIR="$STAGE_DIR/$PACKAGE_NAME"
fi

if [[ -z "$ARCH" ]]; then
    ARCH="amd64"
    PACKAGE_NAME="wok_${VERSION}_${ARCH}"
    PACKAGE_DIR="$STAGE_DIR/$PACKAGE_NAME"
fi

if [[ "${WOK_SKIP_BUILD:-0}" != "1" ]]; then
    cargo "${BUILD_ARGS[@]}"
fi

if [ ! -f "$BINARY_PATH" ]; then
    printf "Error: Binary not found at %s. Run 'cargo build --release -p wok' first.\n" "$BINARY_PATH" >&2
    exit 1
fi

mkdir -p \
    "$PACKAGE_DIR/DEBIAN" \
    "$PACKAGE_DIR/usr/bin" \
    "$PACKAGE_DIR/usr/share/applications" \
    "$PACKAGE_DIR/usr/share/icons/hicolor/256x256/apps" \
    "$PACKAGE_DIR/usr/share/man/man1"

cp "$BINARY_PATH" "$PACKAGE_DIR/usr/bin/wok"
cp "$ROOT_DIR/packaging/linux/wok.desktop" \
    "$PACKAGE_DIR/usr/share/applications/wok.desktop"

# include shell integration scripts
if [ -d "$ROOT_DIR/shell-integration" ]; then
    mkdir -p "$PACKAGE_DIR/usr/share/wok/shell-integration"
    cp "$ROOT_DIR/shell-integration"/* "$PACKAGE_DIR/usr/share/wok/shell-integration/"
fi

python3 - "$PACKAGE_DIR/usr/share/icons/hicolor/256x256/apps/wok.png" <<'PY'
import base64
import sys

data = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4////fwAJ+wP9KobjigAAAABJRU5ErkJggg=="
with open(sys.argv[1], "wb") as handle:
    handle.write(base64.b64decode(data))
PY

python3 - "$PACKAGE_DIR/usr/share/man/man1/wok.1.gz" <<'PY'
import gzip
import sys

content = """.TH WOK 1 "Wok"
.SH NAME
wok \\- GPU-accelerated local-first workspace terminal
"""
with gzip.open(sys.argv[1], "wb", compresslevel=9, mtime=0) as handle:
    handle.write(content.encode("utf-8"))
PY

cat > "$PACKAGE_DIR/DEBIAN/control" <<EOF
Package: wok
Version: $VERSION
Section: utils
Priority: optional
Architecture: $ARCH
Maintainer: Wok Contributors
Description: GPU-accelerated local-first workspace terminal
EOF

mkdir -p "$OUTPUT_DIR"
dpkg-deb --build "$PACKAGE_DIR" "$OUTPUT_DIR/$PACKAGE_NAME.deb" >/dev/null
printf 'Built %s\n' "$OUTPUT_DIR/$PACKAGE_NAME.deb"
