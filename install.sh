#!/bin/bash

set -euo pipefail

MODE="package"
if [[ "${1:-}" == "--source" ]]; then
    MODE="source"
fi

echo "Installing poor-cli (${MODE} mode)..."

python3 -m pip install --upgrade pip

if [[ "$MODE" == "source" ]]; then
    python3 -m pip install ".[all]"
    echo ""
    echo "Installed the current checkout for development."
else
    python3 -m pip install --upgrade poor-cli
    echo ""
    echo "Installed the published poor-cli package."
fi

echo ""
echo "Quick start:"
echo "  poor-cli install-info"
echo "  poor-cli"
echo ""
echo "Provider setup:"
echo "  Configure keys in your shell, in .env, or directly in the TUI setup flow."
echo ""
echo "Development install:"
echo "  ./install.sh --source"
