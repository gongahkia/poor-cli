#!/bin/bash
# install_nvim_plugin.sh
# Manual installation script for nvim-poor-cli Neovim plugin

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_SRC="$SCRIPT_DIR/nvim-poor-cli"
PLUGIN_DEST="$HOME/.local/share/nvim/site/pack/poor-cli/start/nvim-poor-cli"

echo "=== nvim-poor-cli Installation Script ==="
echo ""

# Check source exists
if [ ! -d "$PLUGIN_SRC" ]; then
    echo "Error: Plugin source not found at $PLUGIN_SRC"
    exit 1
fi

# Check for Neovim
if ! command -v nvim &> /dev/null; then
    echo "Error: Neovim not found. Please install Neovim first."
    exit 1
fi

echo "Neovim found: $(nvim --version | head -1)"

# Check for poor-cli-server
if command -v poor-cli-server &> /dev/null; then
    echo "poor-cli-server found: $(which poor-cli-server)"
else
    echo "Warning: poor-cli-server not found in PATH"
    echo "         Install with: pip install poor-cli"
fi

# Create destination directory
echo ""
echo "Installing to: $PLUGIN_DEST"
mkdir -p "$(dirname "$PLUGIN_DEST")"

# Remove existing installation
if [ -d "$PLUGIN_DEST" ]; then
    echo "Removing existing installation..."
    rm -rf "$PLUGIN_DEST"
fi

# Copy plugin
echo "Copying plugin files..."
cp -r "$PLUGIN_SRC" "$PLUGIN_DEST"

echo ""
echo "=== Installation Complete ==="
echo ""
echo "Add the following to your Neovim config:"
echo ""
echo "  -- init.lua"
echo '  require("poor-cli").setup({'
echo "      -- your options here"
echo "  })"
echo ""
echo "Or for init.vim:"
echo ""
echo "  lua require('poor-cli').setup({})"
echo ""
echo "Run :checkhealth poor-cli to verify the installation."
echo ""
