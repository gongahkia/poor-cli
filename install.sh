#!/bin/bash

# Installation script for poor-cli

set -e

echo "╔══════════════════════════════════════╗"
echo "║   Installing poor-cli globally...   ║"
echo "╚══════════════════════════════════════╝"
echo ""

# Check if .env file exists
if [ ! -f .env ]; then
    echo "⚠️  Warning: .env file not found!"
    echo "   You'll need to set GEMINI_API_KEY environment variable"
    echo "   or create a .env file in your project directories"
    echo ""
fi

# Check if running in virtual environment
if [ -n "$VIRTUAL_ENV" ]; then
    echo "⚠️  Warning: You're in a virtual environment!"
    echo "   The command will only be available in this environment."
    echo "   Deactivate to install globally or continue for venv install."
    echo ""
    read -p "Continue? (y/n) " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Install in editable mode for development
echo "📦 Installing poor-cli..."
pip install -e .

echo ""
echo "✅ Installation complete!"
echo ""
echo "╔══════════════════════════════════════╗"
echo "║  You can now use 'poor-cli' from     ║"
echo "║  anywhere in your terminal!          ║"
echo "╚══════════════════════════════════════╝"
echo ""
echo "Quick start:"
echo "  1. Set your GEMINI_API_KEY environment variable:"
echo "     export GEMINI_API_KEY='your-api-key-here'"
echo ""
echo "  2. Run poor-cli from any directory:"
echo "     poor-cli"
echo ""
echo "  3. Or add GEMINI_API_KEY to your ~/.bashrc or ~/.zshrc"
echo ""
