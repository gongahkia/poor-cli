#!/bin/bash

# Quick start script for poor-cli

# Check if .env exists
if [ ! -f .env ]; then
    echo "Error: .env file not found!"
    echo "Please create a .env file with your GEMINI_API_KEY"
    echo "Example: cp .env.example .env"
    exit 1
fi

# Load environment variables
export $(cat .env | xargs)

# Run poor-cli
python3 -m poor_cli
