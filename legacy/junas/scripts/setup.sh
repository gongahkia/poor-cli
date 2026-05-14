#!/usr/bin/env bash
set -euo pipefail
echo "==> checking rust toolchain..."
if ! command -v rustc &>/dev/null; then
  echo "installing rust via rustup..."
  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
  source "$HOME/.cargo/env"
fi
echo "rust $(rustc --version)"
echo "==> checking tauri prerequisites (macOS)..."
if [[ "$(uname)" == "Darwin" ]]; then
  if ! command -v brew &>/dev/null; then echo "error: homebrew required"; exit 1; fi
  xcode-select --install 2>/dev/null || true
fi
echo "==> installing npm dependencies..."
npm install
echo "==> verifying cargo build..."
(cd src-tauri && cargo check)
echo "==> setup complete! run 'npm run tauri:dev' to start."
