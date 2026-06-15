#!/usr/bin/env bash
set -euo pipefail

YES=0
RUN_ID="swe10-local-$(date -u +%Y%m%dT%H%M%SZ)"
ENGINE="${POOR_CLI_LOCAL_ENGINE:-vllm}"
MODEL="${POOR_CLI_LOCAL_MODEL:-Qwen/Qwen2.5-Coder-32B-Instruct}"
DEMO_EVIDENCE="bench/results/phase3-demo.json"
SKIP_SETUP=0
SKIP_GENERATE=0
SKIP_EVALUATE=0
SKIP_DEMO_VERIFY=0
START_SERVER=0
EVAL_MAX_WORKERS=1
TIMEOUT_SECONDS=1200
HEALTH_TIMEOUT_SECONDS=300
SERVER_LOG=".poor-cli/phase3-closeout-server.log"

usage() {
  cat <<'EOF'
usage: scripts/phase3-closeout-linux-cuda.sh --yes [options]

Runs the Phase 3 target-host closeout sequence:
  1. setup Linux/CUDA local model env
  2. refresh readiness
  3. run graph-mode local SWE-bench Lite generation
  4. run official SWE-bench evaluation
  5. verify local benchmark and demo evidence
  6. refresh acceptance, pivot, and closeout snapshots

Options:
  --run-id ID              default: swe10-local-YYYYMMDDTHHMMSSZ
  --engine ENGINE          vllm|sglang|ollama; default: $POOR_CLI_LOCAL_ENGINE or vllm
  --model MODEL            default: Qwen/Qwen2.5-Coder-32B-Instruct
  --demo-evidence PATH     default: bench/results/phase3-demo.json
  --eval-max-workers N     default: 1
  --timeout-seconds N      default: 1200
  --health-timeout-seconds N default: 300
  --server-log PATH        default: .poor-cli/phase3-closeout-server.log
  --start-server           start .poor-cli/local-cuda-run.sh in the background and wait for health
  --skip-setup
  --skip-generate
  --skip-evaluate
  --skip-demo-verify
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --yes) YES=1 ;;
    --run-id) RUN_ID="$2"; shift ;;
    --engine) ENGINE="$2"; shift ;;
    --model) MODEL="$2"; shift ;;
    --demo-evidence) DEMO_EVIDENCE="$2"; shift ;;
    --eval-max-workers) EVAL_MAX_WORKERS="$2"; shift ;;
    --timeout-seconds) TIMEOUT_SECONDS="$2"; shift ;;
    --health-timeout-seconds) HEALTH_TIMEOUT_SECONDS="$2"; shift ;;
    --server-log) SERVER_LOG="$2"; shift ;;
    --start-server) START_SERVER=1 ;;
    --skip-setup) SKIP_SETUP=1 ;;
    --skip-generate) SKIP_GENERATE=1 ;;
    --skip-evaluate) SKIP_EVALUATE=1 ;;
    --skip-demo-verify) SKIP_DEMO_VERIFY=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown arg: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

if [[ "$YES" != "1" ]]; then
  echo "refusing to run Phase 3 closeout without --yes" >&2
  exit 2
fi

if [[ "$SKIP_SETUP" != "1" ]]; then
  scripts/setup-linux-cuda.sh --yes --engine "$ENGINE" --model "$MODEL"
fi

set -a
# shellcheck disable=SC1091
source .poor-cli/local-cuda.env
set +a

uv run --locked python bench/phase3_readiness.py --output bench/results/phase3-readiness.json

case "${POOR_CLI_PROVIDER:-}" in
  vllm|sglang) HEALTH_URL="${POOR_CLI_LOCAL_BASE_URL}/v1/models" ;;
  ollama) HEALTH_URL="${POOR_CLI_LOCAL_BASE_URL}/api/tags" ;;
  *) echo "unsupported POOR_CLI_PROVIDER: ${POOR_CLI_PROVIDER:-}" >&2; exit 2 ;;
esac

server_healthy() {
  curl --fail --silent --show-error --max-time 5 "$HEALTH_URL" >/dev/null
}

wait_for_server() {
  local deadline
  deadline=$((SECONDS + HEALTH_TIMEOUT_SECONDS))
  until server_healthy; do
    if (( SECONDS >= deadline )); then
      return 1
    fi
    sleep 5
  done
}

if [[ "$START_SERVER" == "1" ]] && ! server_healthy; then
  mkdir -p "$(dirname "$SERVER_LOG")"
  nohup .poor-cli/local-cuda-run.sh > "$SERVER_LOG" 2>&1 &
  echo "$!" > .poor-cli/phase3-closeout-server.pid
fi

if ! wait_for_server; then
  echo "local model server is not reachable at $HEALTH_URL; start .poor-cli/local-cuda-run.sh first" >&2
  if [[ "$START_SERVER" == "1" ]]; then
    echo "server log: $SERVER_LOG" >&2
  fi
  exit 2
fi

if [[ "$SKIP_GENERATE" != "1" ]]; then
  uv run --locked --extra bench python bench/swe_bench_lite/run.py \
    --graph \
    --agent local \
    --provider "$POOR_CLI_PROVIDER" \
    --model "$POOR_CLI_MODEL" \
    --local-base-url "$POOR_CLI_LOCAL_BASE_URL" \
    --no-evaluate \
    --confirm-cost \
    --timeout-seconds "$TIMEOUT_SECONDS" \
    --run-id "$RUN_ID"
fi

if [[ "$SKIP_EVALUATE" != "1" ]]; then
  uv run --locked --extra bench python bench/swe_bench_lite/run.py \
    --evaluate-existing-run "$RUN_ID" \
    --confirm-cost \
    --eval-max-workers "$EVAL_MAX_WORKERS" \
    --eval-namespace none
fi

uv run --locked python bench/phase3_local_benchmark.py --summary "bench/swe_bench_lite/results/${RUN_ID}/summary.json"

if [[ "$SKIP_DEMO_VERIFY" != "1" ]]; then
  uv run --locked python bench/phase3_demo.py --evidence "$DEMO_EVIDENCE"
fi

uv run --locked python bench/phase3_acceptance.py --output bench/results/phase3-acceptance.json
uv run --locked python bench/pivot_remaining.py --output bench/results/pivot-remaining.json
uv run --locked python bench/phase3_closeout.py --output bench/results/phase3-closeout.json
