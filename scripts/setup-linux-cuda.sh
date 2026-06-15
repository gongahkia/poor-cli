#!/usr/bin/env bash
set -euo pipefail

ENGINE="${POOR_CLI_LOCAL_ENGINE:-vllm}"
MODEL="${POOR_CLI_LOCAL_MODEL:-Qwen/Qwen2.5-Coder-32B-Instruct}"
VENV="${POOR_CLI_LOCAL_VENV:-.poor-cli/local-cuda-venv}"
HOST="${POOR_CLI_LOCAL_HOST:-127.0.0.1}"
PORT="${POOR_CLI_LOCAL_PORT:-}"
PREFIX_CACHE="${POOR_CLI_LOCAL_PREFIX_CACHE:-1}"
PREFIX_CACHE_HASH_ALGO="${POOR_CLI_LOCAL_PREFIX_CACHE_HASH_ALGO:-sha256}"
KV_CACHE_DTYPE="${POOR_CLI_LOCAL_KV_CACHE_DTYPE:-auto}"
YES=0
SKIP_CUDA_CHECK=0
SKIP_ENGINE_INSTALL=0

usage() {
  cat <<'EOF'
usage: scripts/setup-linux-cuda.sh --yes [--engine vllm|sglang|ollama] [--model MODEL] [--venv PATH]

Creates a Linux CUDA local-first poor-cli environment and writes:
  .poor-cli/local-cuda.env
  .poor-cli/local-cuda-run.sh

Environment overrides:
  POOR_CLI_LOCAL_ENGINE=vllm|sglang|ollama
  POOR_CLI_LOCAL_MODEL=Qwen/Qwen2.5-Coder-32B-Instruct
  POOR_CLI_LOCAL_VENV=.poor-cli/local-cuda-venv
  POOR_CLI_LOCAL_HOST=127.0.0.1
  POOR_CLI_LOCAL_PORT=8000
  POOR_CLI_LOCAL_PREFIX_CACHE=1
  POOR_CLI_LOCAL_PREFIX_CACHE_HASH_ALGO=sha256
  POOR_CLI_LOCAL_KV_CACHE_DTYPE=auto
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --yes) YES=1 ;;
    --engine) ENGINE="$2"; shift ;;
    --model) MODEL="$2"; shift ;;
    --venv) VENV="$2"; shift ;;
    --host) HOST="$2"; shift ;;
    --port) PORT="$2"; shift ;;
    --prefix-cache) PREFIX_CACHE=1 ;;
    --no-prefix-cache) PREFIX_CACHE=0 ;;
    --prefix-cache-hash-algo) PREFIX_CACHE_HASH_ALGO="$2"; shift ;;
    --kv-cache-dtype) KV_CACHE_DTYPE="$2"; shift ;;
    --skip-cuda-check) SKIP_CUDA_CHECK=1 ;;
    --skip-engine-install) SKIP_ENGINE_INSTALL=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown arg: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

if [[ "$YES" != "1" ]]; then
  echo "refusing to install CUDA/local-model packages without --yes" >&2
  exit 2
fi
if [[ "$(uname -s)" != "Linux" && "${POOR_CLI_ALLOW_NON_LINUX:-0}" != "1" ]]; then
  echo "Linux required; set POOR_CLI_ALLOW_NON_LINUX=1 only for dry validation" >&2
  exit 2
fi
if [[ "$SKIP_CUDA_CHECK" != "1" ]] && ! command -v nvidia-smi >/dev/null 2>&1; then
  echo "nvidia-smi not found; install NVIDIA driver/CUDA first or pass --skip-cuda-check" >&2
  exit 2
fi

case "$ENGINE" in
  vllm) DEFAULT_PORT="8000"; ENGINE_PACKAGE="vllm"; PROVIDER="vllm" ;;
  sglang) DEFAULT_PORT="30000"; ENGINE_PACKAGE="sglang[all]"; PROVIDER="sglang" ;;
  ollama) DEFAULT_PORT="11434"; ENGINE_PACKAGE=""; PROVIDER="ollama" ;;
  *) echo "unsupported engine: $ENGINE" >&2; exit 2 ;;
esac
if [[ "$PORT" == "" ]]; then
  PORT="$DEFAULT_PORT"
fi

python3 -m venv "$VENV"
# shellcheck disable=SC1091
source "$VENV/bin/activate"
python -m pip install --upgrade pip wheel
python -m pip install -e ".[providers]"
if [[ "$SKIP_ENGINE_INSTALL" != "1" && "$ENGINE_PACKAGE" != "" ]]; then
  python -m pip install "$ENGINE_PACKAGE"
fi
mkdir -p .poor-cli

BASE_URL="http://${HOST}:${PORT}"
if [[ "$ENGINE" == "ollama" ]]; then
  PROVIDER_URL="${BASE_URL}"
else
  PROVIDER_URL="${BASE_URL}/v1"
fi

cat > .poor-cli/local-cuda.env <<EOF
POOR_CLI_LOCAL_ENGINE=$ENGINE
POOR_CLI_LOCAL_MODEL=$MODEL
POOR_CLI_LOCAL_BASE_URL=$BASE_URL
POOR_CLI_LOCAL_PREFIX_CACHE=$PREFIX_CACHE
POOR_CLI_LOCAL_PREFIX_CACHE_HASH_ALGO=$PREFIX_CACHE_HASH_ALGO
POOR_CLI_LOCAL_KV_CACHE_DTYPE=$KV_CACHE_DTYPE
POOR_CLI_PROVIDER=$PROVIDER
POOR_CLI_MODEL=$MODEL
EOF

case "$ENGINE" in
  vllm)
    CACHE_ARGS=""
    if [[ "$PREFIX_CACHE" == "1" ]]; then
      CACHE_ARGS=" --enable-prefix-caching --prefix-caching-hash-algo '$PREFIX_CACHE_HASH_ALGO'"
    else
      CACHE_ARGS=" --no-enable-prefix-caching"
    fi
    if [[ "$KV_CACHE_DTYPE" != "auto" ]]; then
      CACHE_ARGS="${CACHE_ARGS} --kv-cache-dtype '$KV_CACHE_DTYPE'"
    fi
    LAUNCH_CMD="source '$VENV/bin/activate' && vllm serve '$MODEL' --host '$HOST' --port '$PORT'$CACHE_ARGS"
    ;;
  sglang)
    CACHE_ARGS=""
    if [[ "$PREFIX_CACHE" != "1" ]]; then
      CACHE_ARGS=" --disable-radix-cache"
    fi
    if [[ "$KV_CACHE_DTYPE" != "auto" ]]; then
      CACHE_ARGS="${CACHE_ARGS} --kv-cache-dtype '$KV_CACHE_DTYPE'"
    fi
    LAUNCH_CMD="source '$VENV/bin/activate' && python -m sglang.launch_server --model-path '$MODEL' --host '$HOST' --port '$PORT'$CACHE_ARGS"
    ;;
  ollama)
    LAUNCH_CMD="ollama serve"
    ;;
esac

cat > .poor-cli/local-cuda-run.sh <<EOF
#!/usr/bin/env bash
set -euo pipefail
$LAUNCH_CMD
EOF
chmod +x .poor-cli/local-cuda-run.sh

echo "local engine: $ENGINE"
echo "model: $MODEL"
echo "provider URL: $PROVIDER_URL"
echo "env: .poor-cli/local-cuda.env"
echo "launch: .poor-cli/local-cuda-run.sh"
