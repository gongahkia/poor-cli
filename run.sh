#!/bin/bash

# Quick start script for poor-cli
set -euo pipefail

# Check if .env exists
if [ ! -f .env ]; then
    echo "Error: .env file not found!"
    echo "Please create a .env file with your GEMINI_API_KEY"
    echo "Example: cp .env.example .env"
    exit 1
fi

load_env_file() {
    local env_file="$1"
    local line

    while IFS= read -r line || [[ -n "$line" ]]; do
        # Normalize CRLF endings.
        line="${line%$'\r'}"

        # Skip blank lines and full-line comments.
        [[ -z "${line//[[:space:]]/}" ]] && continue
        [[ "$line" =~ ^[[:space:]]*# ]] && continue

        # Support optional `export KEY=VALUE` format.
        if [[ "$line" =~ ^[[:space:]]*export[[:space:]]+ ]]; then
            line="${line#export }"
            line="${line#"${line%%[![:space:]]*}"}"
        fi

        [[ "$line" != *"="* ]] && continue

        local key="${line%%=*}"
        local value="${line#*=}"

        # Trim surrounding whitespace from key only.
        key="${key#"${key%%[![:space:]]*}"}"
        key="${key%"${key##*[![:space:]]}"}"

        # Remove matching quote wrappers around value.
        if [[ "$value" =~ ^\".*\"$ ]]; then
            value="${value:1:${#value}-2}"
        elif [[ "$value" =~ ^\'.*\'$ ]]; then
            value="${value:1:${#value}-2}"
        fi

        # Skip invalid environment variable names.
        if [[ ! "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
            continue
        fi

        export "${key}=${value}"
    done < "$env_file"
}

# Load environment variables from .env safely.
load_env_file ".env"

# Run poor-cli
clear && python3 -m poor_cli
