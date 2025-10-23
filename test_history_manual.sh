#!/bin/bash

# Test script to verify history logging works
# This will simulate a user session and check if history is saved

echo "Testing history logging..."
echo ""

# Clean up any existing test history
rm -rf .poor-cli

# Create a test session
echo "Starting test session..."
cat << 'EOF' | GEMINI_API_KEY=AIzaSyDuSdhX6VsvZi1Mwvg315wiGVhrTgQleDw timeout 10 .venv/bin/poor-cli 2>&1 | head -100
hello
/history
/quit
EOF

echo ""
echo "Checking if history was saved..."
echo ""

if [ -f ".poor-cli/history.json" ]; then
    echo "✓ History file exists: .poor-cli/history.json"
    echo ""
    echo "Contents:"
    cat .poor-cli/history.json | python3 -m json.tool | head -50
    echo ""
else
    echo "✗ History file not found!"
    echo ""
    echo "Checking directory:"
    ls -la .poor-cli/
fi

echo ""
echo "Test complete!"
