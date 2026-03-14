#!/usr/bin/env bash
# Run the poor-cli Rust TUI.
#
# This script builds the Rust TUI (if needed) and launches it.
# It passes all arguments through to the binary.
#
# Usage:
#   ./run_tui.sh                        # Interactive TUI
#   ./run_tui.sh --provider ollama      # Use local Ollama models
#   ./run_tui.sh --provider gemini      # Use Gemini
#   ./run_tui.sh --help                 # Show all options

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TUI_DIR="${SCRIPT_DIR}/poor-cli-tui"
BINARY="${TUI_DIR}/target/release/poor-cli-tui"

# Load .env if present so direct `./run_tui.sh` matches `./run.sh` behavior.
if [ -f "${SCRIPT_DIR}/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "${SCRIPT_DIR}/.env"
    set +a
fi

# Build if binary doesn't exist or source is newer
if [ ! -f "$BINARY" ] || [ "$(find "$TUI_DIR/src" -newer "$BINARY" -print -quit 2>/dev/null)" ]; then
    # Source cargo env only when a build is required.
    if [ -f "$HOME/.cargo/env" ]; then
        source "$HOME/.cargo/env"
    fi

    if ! command -v cargo &>/dev/null; then
        echo "Error: Rust/Cargo not found. Install from https://rustup.rs/ or provide a prebuilt poor-cli-tui binary."
        exit 1
    fi

    echo "Building poor-cli-tui..."
    if ! (cd "$TUI_DIR" && cargo build --release 2>&1); then
        echo "Error: cargo build failed. Check the output above for details."
        exit 1
    fi
    echo "Build complete."
fi

if [ ! -x "$BINARY" ]; then
    echo "Error: poor-cli-tui binary not found at $BINARY"
    exit 1
fi

# Run the TUI, forwarding all arguments
exec "$BINARY" "$@"
