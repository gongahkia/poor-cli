#!/bin/bash

# Uninstallation script for poor-cli

set -e

echo "╔══════════════════════════════════════╗"
echo "║  Uninstalling poor-cli...            ║"
echo "╚══════════════════════════════════════╝"
echo ""

# Uninstall the package
pip uninstall -y poor-cli

echo ""
echo "✅ poor-cli has been uninstalled"
echo ""
