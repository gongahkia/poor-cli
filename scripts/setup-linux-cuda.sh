#!/usr/bin/env bash
set -euo pipefail

ENGINE="${POOR_CLI_LOCAL_ENGINE:-vllm}"
MODEL="${POOR_CLI_LOCAL_MODEL:-Qwen/Qwen2.5-Coder-32B-Instruct}"
SERVED_MODEL="${POOR_CLI_LOCAL_SERVED_MODEL:-}"
PYTHON="${POOR_CLI_LOCAL_PYTHON:-python3}"
VENV="${POOR_CLI_LOCAL_VENV:-.poor-cli/local-cuda-venv}"
HOST="${POOR_CLI_LOCAL_HOST:-127.0.0.1}"
PORT="${POOR_CLI_LOCAL_PORT:-}"
PREFIX_CACHE="${POOR_CLI_LOCAL_PREFIX_CACHE:-1}"
PREFIX_CACHE_HASH_ALGO="${POOR_CLI_LOCAL_PREFIX_CACHE_HASH_ALGO:-sha256}"
KV_CACHE_DTYPE="${POOR_CLI_LOCAL_KV_CACHE_DTYPE:-auto}"
QUANTIZATION="${POOR_CLI_LOCAL_QUANTIZATION:-}"
DTYPE="${POOR_CLI_LOCAL_DTYPE:-auto}"
MAX_MODEL_LEN="${POOR_CLI_LOCAL_MAX_MODEL_LEN:-}"
TENSOR_PARALLEL_SIZE="${POOR_CLI_LOCAL_TENSOR_PARALLEL_SIZE:-}"
GPU_MEMORY_UTILIZATION="${POOR_CLI_LOCAL_GPU_MEMORY_UTILIZATION:-}"
YES=0
SERVED_MODEL_SET=0
SKIP_CUDA_CHECK=0
SKIP_ENGINE_INSTALL=0

usage() {
  cat <<'EOF'
usage: scripts/setup-linux-cuda.sh --yes [--engine vllm|sglang|ollama] [--model MODEL] [--served-model MODEL] [--python PYTHON] [--venv PATH]

Creates a Linux CUDA local-first poor-cli environment and writes:
  .poor-cli/local-cuda.env
  .poor-cli/local-cuda-run.sh

Environment overrides:
  POOR_CLI_LOCAL_ENGINE=vllm|sglang|ollama
  POOR_CLI_LOCAL_MODEL=Qwen/Qwen2.5-Coder-32B-Instruct
  POOR_CLI_LOCAL_SERVED_MODEL=Qwen/Qwen2.5-Coder-32B-Instruct
  POOR_CLI_LOCAL_PYTHON=python3
  POOR_CLI_LOCAL_VENV=.poor-cli/local-cuda-venv
  POOR_CLI_LOCAL_HOST=127.0.0.1
  POOR_CLI_LOCAL_PORT=8000
  POOR_CLI_LOCAL_PREFIX_CACHE=1
  POOR_CLI_LOCAL_PREFIX_CACHE_HASH_ALGO=sha256
  POOR_CLI_LOCAL_KV_CACHE_DTYPE=auto
  POOR_CLI_LOCAL_QUANTIZATION=awq
  POOR_CLI_LOCAL_DTYPE=auto
  POOR_CLI_LOCAL_MAX_MODEL_LEN=8192
  POOR_CLI_LOCAL_TENSOR_PARALLEL_SIZE=1
  POOR_CLI_LOCAL_GPU_MEMORY_UTILIZATION=0.90
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --yes) YES=1 ;;
    --engine) ENGINE="$2"; shift ;;
    --model) MODEL="$2"; shift ;;
    --served-model) SERVED_MODEL="$2"; SERVED_MODEL_SET=1; shift ;;
    --python) PYTHON="$2"; shift ;;
    --venv) VENV="$2"; shift ;;
    --host) HOST="$2"; shift ;;
    --port) PORT="$2"; shift ;;
    --prefix-cache) PREFIX_CACHE=1 ;;
    --no-prefix-cache) PREFIX_CACHE=0 ;;
    --prefix-cache-hash-algo) PREFIX_CACHE_HASH_ALGO="$2"; shift ;;
    --kv-cache-dtype) KV_CACHE_DTYPE="$2"; shift ;;
    --quantization) QUANTIZATION="$2"; shift ;;
    --dtype) DTYPE="$2"; shift ;;
    --max-model-len) MAX_MODEL_LEN="$2"; shift ;;
    --tensor-parallel-size) TENSOR_PARALLEL_SIZE="$2"; shift ;;
    --gpu-memory-utilization) GPU_MEMORY_UTILIZATION="$2"; shift ;;
    --skip-cuda-check) SKIP_CUDA_CHECK=1 ;;
    --skip-engine-install) SKIP_ENGINE_INSTALL=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown arg: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

if [[ "$SERVED_MODEL_SET" != "1" && "$SERVED_MODEL" == "" ]]; then
  SERVED_MODEL="$MODEL"
fi

if [[ "$YES" != "1" ]]; then
  echo "refusing to install CUDA/local-model packages without --yes" >&2
  exit 2
fi
if [[ "$(uname -s)" != "Linux" && "${POOR_CLI_ALLOW_NON_LINUX:-0}" != "1" ]]; then
  echo "Linux required; set POOR_CLI_ALLOW_NON_LINUX=1 only for dry validation" >&2
  exit 2
fi
if [[ "$SKIP_CUDA_CHECK" != "1" ]]; then
  if ! command -v nvidia-smi >/dev/null 2>&1; then
    echo "nvidia-smi not found; install NVIDIA driver/CUDA first or pass --skip-cuda-check" >&2
    exit 2
  fi
  set +e
  GPU_QUERY="$(nvidia-smi --query-gpu=name --format=csv,noheader 2>&1)"
  GPU_QUERY_EXIT="$?"
  set -e
  if [[ "$GPU_QUERY_EXIT" != "0" || "$GPU_QUERY" == "" ]]; then
    echo "nvidia-smi did not return a GPU name; check NVIDIA driver/CUDA before setup or pass --skip-cuda-check for dry validation" >&2
    echo "$GPU_QUERY" >&2
    exit 2
  fi
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

"$PYTHON" -m venv "$VENV"
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

{
  printf 'export POOR_CLI_LOCAL_ENGINE=%q\n' "$ENGINE"
  printf 'export POOR_CLI_LOCAL_MODEL=%q\n' "$SERVED_MODEL"
  printf 'export POOR_CLI_LOCAL_MODEL_SOURCE=%q\n' "$MODEL"
  printf 'export POOR_CLI_LOCAL_SERVED_MODEL=%q\n' "$SERVED_MODEL"
  printf 'export POOR_CLI_LOCAL_PYTHON=%q\n' "$PYTHON"
  printf 'export POOR_CLI_LOCAL_VENV=%q\n' "$VENV"
  printf 'export POOR_CLI_LOCAL_BASE_URL=%q\n' "$BASE_URL"
  printf 'export POOR_CLI_LOCAL_PREFIX_CACHE=%q\n' "$PREFIX_CACHE"
  printf 'export POOR_CLI_LOCAL_PREFIX_CACHE_HASH_ALGO=%q\n' "$PREFIX_CACHE_HASH_ALGO"
  printf 'export POOR_CLI_LOCAL_KV_CACHE_DTYPE=%q\n' "$KV_CACHE_DTYPE"
  printf 'export POOR_CLI_LOCAL_QUANTIZATION=%q\n' "$QUANTIZATION"
  printf 'export POOR_CLI_LOCAL_DTYPE=%q\n' "$DTYPE"
  printf 'export POOR_CLI_LOCAL_MAX_MODEL_LEN=%q\n' "$MAX_MODEL_LEN"
  printf 'export POOR_CLI_LOCAL_TENSOR_PARALLEL_SIZE=%q\n' "$TENSOR_PARALLEL_SIZE"
  printf 'export POOR_CLI_LOCAL_GPU_MEMORY_UTILIZATION=%q\n' "$GPU_MEMORY_UTILIZATION"
  printf 'export POOR_CLI_PROVIDER=%q\n' "$PROVIDER"
  printf 'export POOR_CLI_MODEL=%q\n' "$SERVED_MODEL"
} > .poor-cli/local-cuda.env

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
    MODEL_ARGS=" --served-model-name '$SERVED_MODEL'"
    if [[ "$QUANTIZATION" != "" ]]; then MODEL_ARGS="${MODEL_ARGS} --quantization '$QUANTIZATION'"; fi
    if [[ "$DTYPE" != "auto" ]]; then MODEL_ARGS="${MODEL_ARGS} --dtype '$DTYPE'"; fi
    if [[ "$MAX_MODEL_LEN" != "" ]]; then MODEL_ARGS="${MODEL_ARGS} --max-model-len '$MAX_MODEL_LEN'"; fi
    if [[ "$TENSOR_PARALLEL_SIZE" != "" ]]; then MODEL_ARGS="${MODEL_ARGS} --tensor-parallel-size '$TENSOR_PARALLEL_SIZE'"; fi
    if [[ "$GPU_MEMORY_UTILIZATION" != "" ]]; then MODEL_ARGS="${MODEL_ARGS} --gpu-memory-utilization '$GPU_MEMORY_UTILIZATION'"; fi
    LAUNCH_CMD="source '$VENV/bin/activate' && exec vllm serve '$MODEL' --host '$HOST' --port '$PORT'$MODEL_ARGS$CACHE_ARGS"
    ;;
  sglang)
    CACHE_ARGS=""
    if [[ "$PREFIX_CACHE" != "1" ]]; then
      CACHE_ARGS=" --disable-radix-cache"
    fi
    if [[ "$KV_CACHE_DTYPE" != "auto" ]]; then
      CACHE_ARGS="${CACHE_ARGS} --kv-cache-dtype '$KV_CACHE_DTYPE'"
    fi
    MODEL_ARGS=" --served-model-name '$SERVED_MODEL'"
    if [[ "$QUANTIZATION" != "" ]]; then MODEL_ARGS="${MODEL_ARGS} --quantization '$QUANTIZATION'"; fi
    if [[ "$DTYPE" != "auto" ]]; then MODEL_ARGS="${MODEL_ARGS} --dtype '$DTYPE'"; fi
    if [[ "$MAX_MODEL_LEN" != "" ]]; then MODEL_ARGS="${MODEL_ARGS} --context-length '$MAX_MODEL_LEN'"; fi
    if [[ "$TENSOR_PARALLEL_SIZE" != "" ]]; then MODEL_ARGS="${MODEL_ARGS} --tensor-parallel-size '$TENSOR_PARALLEL_SIZE'"; fi
    if [[ "$GPU_MEMORY_UTILIZATION" != "" ]]; then MODEL_ARGS="${MODEL_ARGS} --mem-fraction-static '$GPU_MEMORY_UTILIZATION'"; fi
    LAUNCH_CMD="source '$VENV/bin/activate' && exec python -m sglang.launch_server --model-path '$MODEL' --host '$HOST' --port '$PORT'$MODEL_ARGS$CACHE_ARGS"
    ;;
  ollama)
    LAUNCH_CMD="exec ollama serve"
    ;;
esac

cat > .poor-cli/local-cuda-run.sh <<EOF
#!/usr/bin/env bash
set -euo pipefail
$LAUNCH_CMD
EOF
chmod +x .poor-cli/local-cuda-run.sh

echo "local engine: $ENGINE"
echo "model source: $MODEL"
echo "served model: $SERVED_MODEL"
echo "provider URL: $PROVIDER_URL"
echo "env: .poor-cli/local-cuda.env"
echo "launch: .poor-cli/local-cuda-run.sh"
