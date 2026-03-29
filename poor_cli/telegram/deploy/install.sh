#!/usr/bin/env bash
set -euo pipefail

echo "poor-cli Telegram bot setup"
echo "==========================="

# check Python
if ! command -v python3 &>/dev/null; then
    echo "error: python3 required"
    exit 1
fi

PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "python: $PY_VER"

# install
echo "installing poor-cli with Telegram support..."
pip install 'poor-cli[telegram]'

# prompt for token
if [ -z "${TELEGRAM_TOKEN:-}" ]; then
    read -rp "Telegram bot token: " TELEGRAM_TOKEN
fi

# write .env
ENV_FILE="${HOME}/.poor-cli/telegram.env"
mkdir -p "$(dirname "$ENV_FILE")"
cat > "$ENV_FILE" <<EOF
TELEGRAM_TOKEN=${TELEGRAM_TOKEN}
POOR_CLI_TELEGRAM_TOKEN=${TELEGRAM_TOKEN}
POOR_CLI_PROVIDER=gemini
POOR_CLI_MODEL=gemini-2.5-flash
SANDBOX_PRESET=review-only
EOF

echo "config written to ${ENV_FILE}"
echo ""
echo "start the bot:"
echo "  poor-cli telegram --token \$TELEGRAM_TOKEN"
echo ""
echo "or with env file:"
echo "  export \$(cat ${ENV_FILE} | xargs) && poor-cli telegram"
