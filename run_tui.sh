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

# Source cargo env if available
if [ -f "$HOME/.cargo/env" ]; then
    source "$HOME/.cargo/env"
fi

# Check for cargo
if ! command -v cargo &>/dev/null; then
    echo "Error: Rust/Cargo not found. Install from https://rustup.rs/"
    exit 1
fi

# Build if binary doesn't exist or source is newer
if [ ! -f "$BINARY" ] || [ "$(find "$TUI_DIR/src" -newer "$BINARY" -print -quit 2>/dev/null)" ]; then
    echo "Building poor-cli-tui..."
    (cd "$TUI_DIR" && cargo build --release 2>&1)
    echo "Build complete."
fi

# Run the TUI, forwarding all arguments
exec "$BINARY" "$@"
