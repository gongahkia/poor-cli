#!/usr/bin/env bash
set -euo pipefail

PACKAGE_REF="${HAUS_UVX_REF:-git+https://github.com/gongahkia/haus}"

uvx --from "$PACKAGE_REF" haus --help >/tmp/haus-uvx-help.txt
uvx --from "$PACKAGE_REF" haus mcp --help >/tmp/haus-uvx-mcp-help.txt
uvx --from "$PACKAGE_REF" haus view --help >/tmp/haus-uvx-view-help.txt

grep -qi "usage" /tmp/haus-uvx-help.txt
grep -qi "mcp" /tmp/haus-uvx-mcp-help.txt
grep -qi "view" /tmp/haus-uvx-view-help.txt

echo "Haus macOS uvx smoke passed"
