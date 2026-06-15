#!/usr/bin/env bash
set -euo pipefail

YES=0
RUN_ID="swe10-local-$(date -u +%Y%m%dT%H%M%SZ)"
ENGINE="${POOR_CLI_LOCAL_ENGINE:-vllm}"
MODEL="${POOR_CLI_LOCAL_MODEL:-Qwen/Qwen2.5-Coder-32B-Instruct}"
DEMO_EVIDENCE="bench/results/phase3-demo.json"
DEMO_VIDEO_PATH="bench/results/phase3-demo.mp4"
DEMO_DURATION_SECONDS=60
DEMO_RUN_ID=""
DEMO_STORE_DIR=""
SKIP_SETUP=0
SKIP_GENERATE=0
SKIP_EVALUATE=0
SKIP_DEMO_VERIFY=0
START_SERVER=0
STOP_SERVER_ON_EXIT=0
WRITE_DEMO_EVIDENCE=0
DEMO_INTERNET_DISABLED=0
DEMO_LOCAL_GPU=0
DEMO_GRAPH_TOOLS_VISIBLE=0
DEMO_OFFLINE_REPLAY_VERIFIED=0
EVAL_MAX_WORKERS=1
TIMEOUT_SECONDS=1200
HEALTH_TIMEOUT_SECONDS=300
SERVER_LOG=".poor-cli/phase3-closeout-server.log"
SERVER_PID=""
NETWORK_PROBE_ARGS=(curl --fail --silent --show-error --max-time 5 https://example.com)
NETWORK_PROBE_COMMAND="${NETWORK_PROBE_ARGS[*]}"
NETWORK_PROBE_EXIT_CODE=""
GPU_PROBE_ARGS=(nvidia-smi --query-gpu=name --format=csv,noheader)
GPU_PROBE_COMMAND="${GPU_PROBE_ARGS[*]}"
GPU_PROBE_EXIT_CODE=""
GPU_PROBE_OUTPUT=""

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
  --demo-video-path PATH   default: bench/results/phase3-demo.mp4
  --demo-duration-seconds N default: 60
  --demo-run-id ID         override demo replay run id; default: first verified SWE task run
  --demo-store-dir PATH    override demo replay store dir; default: first verified SWE task store
  --eval-max-workers N     default: 1
  --timeout-seconds N      default: 1200
  --health-timeout-seconds N default: 300
  --server-log PATH        default: .poor-cli/phase3-closeout-server.log
  --start-server           start .poor-cli/local-cuda-run.sh in the background and wait for health
  --stop-server-on-exit    stop the server process started by --start-server when this script exits
  --write-demo-evidence    write bench/results/phase3-demo.json before verification
  --demo-internet-disabled assert the screencast proves internet was disabled
  --demo-local-gpu         assert the screencast proves local GPU execution
  --demo-graph-tools-visible assert graph tools are visible in the screencast
  --demo-offline-replay-verified assert offline replay verification is shown
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
    --demo-video-path) DEMO_VIDEO_PATH="$2"; shift ;;
    --demo-duration-seconds) DEMO_DURATION_SECONDS="$2"; shift ;;
    --demo-run-id) DEMO_RUN_ID="$2"; shift ;;
    --demo-store-dir) DEMO_STORE_DIR="$2"; shift ;;
    --eval-max-workers) EVAL_MAX_WORKERS="$2"; shift ;;
    --timeout-seconds) TIMEOUT_SECONDS="$2"; shift ;;
    --health-timeout-seconds) HEALTH_TIMEOUT_SECONDS="$2"; shift ;;
    --server-log) SERVER_LOG="$2"; shift ;;
    --start-server) START_SERVER=1 ;;
    --stop-server-on-exit) STOP_SERVER_ON_EXIT=1 ;;
    --write-demo-evidence) WRITE_DEMO_EVIDENCE=1 ;;
    --demo-internet-disabled) DEMO_INTERNET_DISABLED=1 ;;
    --demo-local-gpu) DEMO_LOCAL_GPU=1 ;;
    --demo-graph-tools-visible) DEMO_GRAPH_TOOLS_VISIBLE=1 ;;
    --demo-offline-replay-verified) DEMO_OFFLINE_REPLAY_VERIFIED=1 ;;
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

stop_started_server() {
  if [[ "$STOP_SERVER_ON_EXIT" == "1" && "$SERVER_PID" != "" ]]; then
    if kill -0 "$SERVER_PID" >/dev/null 2>&1; then
      kill "$SERVER_PID" >/dev/null 2>&1 || true
      wait "$SERVER_PID" 2>/dev/null || true
    fi
    rm -f .poor-cli/phase3-closeout-server.pid
  fi
}
trap stop_started_server EXIT

if [[ "$SKIP_SETUP" != "1" ]]; then
  scripts/setup-linux-cuda.sh --yes --engine "$ENGINE" --model "$MODEL"
fi

set -a
# shellcheck disable=SC1091
source .poor-cli/local-cuda.env
set +a

uv run --locked python bench/phase3_readiness.py --output bench/results/phase3-readiness.json

openai_compatible_health_url() {
  local base
  base="${1%/}"
  if [[ "$base" == */v1 ]]; then
    printf '%s/models\n' "$base"
  else
    printf '%s/v1/models\n' "$base"
  fi
}

case "${POOR_CLI_PROVIDER:-}" in
  vllm|sglang) HEALTH_URL="$(openai_compatible_health_url "$POOR_CLI_LOCAL_BASE_URL")" ;;
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

derive_demo_replay_evidence() {
  uv run --locked python - "bench/swe_bench_lite/results/${RUN_ID}/task_results.jsonl" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
for line in path.read_text(encoding="utf-8").splitlines():
    if not line.strip():
        continue
    record = json.loads(line)
    run_id = str(record.get("poor_cli_run_id") or "")
    store_dir = str(record.get("poor_cli_store_dir") or "")
    if record.get("replay_verified") and run_id and store_dir:
        print(f"{run_id}\t{store_dir}")
        raise SystemExit(0)
raise SystemExit("no replay-verified SWE task with poor_cli_run_id and poor_cli_store_dir")
PY
}

capture_network_disabled_probe() {
  set +e
  "${NETWORK_PROBE_ARGS[@]}" >/dev/null 2>&1
  NETWORK_PROBE_EXIT_CODE="$?"
  set -e
  if [[ "$NETWORK_PROBE_EXIT_CODE" == "0" ]]; then
    echo "internet-disabled proof failed: ${NETWORK_PROBE_COMMAND} succeeded" >&2
    exit 2
  fi
}

capture_gpu_probe() {
  set +e
  GPU_PROBE_OUTPUT="$("${GPU_PROBE_ARGS[@]}" 2>&1)"
  GPU_PROBE_EXIT_CODE="$?"
  set -e
  if [[ "$GPU_PROBE_EXIT_CODE" != "0" || "$GPU_PROBE_OUTPUT" == "" ]]; then
    echo "local-GPU proof failed: ${GPU_PROBE_COMMAND} did not return a GPU name" >&2
    exit 2
  fi
}

if [[ "$START_SERVER" == "1" ]] && ! server_healthy; then
  mkdir -p "$(dirname "$SERVER_LOG")"
  nohup .poor-cli/local-cuda-run.sh > "$SERVER_LOG" 2>&1 &
  SERVER_PID="$!"
  echo "$SERVER_PID" > .poor-cli/phase3-closeout-server.pid
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

if [[ "$WRITE_DEMO_EVIDENCE" == "1" ]]; then
  if [[ "$DEMO_RUN_ID" == "" || "$DEMO_STORE_DIR" == "" ]]; then
    DEMO_REPLAY_EVIDENCE="$(derive_demo_replay_evidence)"
    DEMO_DERIVED_RUN_ID="${DEMO_REPLAY_EVIDENCE%%$'\t'*}"
    DEMO_DERIVED_STORE_DIR="${DEMO_REPLAY_EVIDENCE#*$'\t'}"
    if [[ "$DEMO_RUN_ID" == "" ]]; then DEMO_RUN_ID="$DEMO_DERIVED_RUN_ID"; fi
    if [[ "$DEMO_STORE_DIR" == "" ]]; then DEMO_STORE_DIR="$DEMO_DERIVED_STORE_DIR"; fi
  fi
  DEMO_FLAGS=()
  if [[ "$DEMO_INTERNET_DISABLED" == "1" ]]; then DEMO_FLAGS+=(--internet-disabled); fi
  if [[ "$DEMO_LOCAL_GPU" == "1" ]]; then DEMO_FLAGS+=(--local-gpu); fi
  if [[ "$DEMO_GRAPH_TOOLS_VISIBLE" == "1" ]]; then DEMO_FLAGS+=(--graph-tools-visible); fi
  if [[ "$DEMO_OFFLINE_REPLAY_VERIFIED" == "1" ]]; then DEMO_FLAGS+=(--offline-replay-verified); fi
  if [[ "$DEMO_INTERNET_DISABLED" == "1" ]]; then
    capture_network_disabled_probe
    DEMO_FLAGS+=(--network-probe-command "$NETWORK_PROBE_COMMAND" --network-probe-exit-code "$NETWORK_PROBE_EXIT_CODE")
  fi
  if [[ "$DEMO_LOCAL_GPU" == "1" ]]; then
    capture_gpu_probe
    DEMO_FLAGS+=(--gpu-probe-command "$GPU_PROBE_COMMAND" --gpu-probe-exit-code "$GPU_PROBE_EXIT_CODE" --gpu-probe-output "$GPU_PROBE_OUTPUT")
  fi
  uv run --locked python bench/phase3_demo.py \
    --write-template "$DEMO_EVIDENCE" \
    --run-id "$DEMO_RUN_ID" \
    --store-dir "$DEMO_STORE_DIR" \
    --video-path "$DEMO_VIDEO_PATH" \
    --duration-seconds "$DEMO_DURATION_SECONDS" \
    --model "$POOR_CLI_MODEL" \
    "${DEMO_FLAGS[@]}"
fi

if [[ "$SKIP_DEMO_VERIFY" != "1" ]]; then
  uv run --locked python bench/phase3_demo.py --evidence "$DEMO_EVIDENCE"
fi

uv run --locked python bench/phase3_acceptance.py --output bench/results/phase3-acceptance.json
uv run --locked python bench/pivot_remaining.py --output bench/results/pivot-remaining.json
uv run --locked python bench/phase3_closeout.py --output bench/results/phase3-closeout.json
