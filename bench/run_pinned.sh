#!/usr/bin/env bash
set -euo pipefail

if [[ $# -eq 0 ]]; then
  echo "usage: bench/run_pinned.sh <command> [args...]" >&2
  exit 2
fi

export PYTHONHASHSEED="${PYTHONHASHSEED:-0}"
export TZ="${TZ:-UTC}"
export LANG="${LANG:-C.UTF-8}"
export LC_ALL="${LC_ALL:-C.UTF-8}"
export POORCLI_BENCH_AUTO_START="${POORCLI_BENCH_AUTO_START:-0}"

pin_cpu="${POORCLI_PERF_PIN_CPU:-0}"

if command -v taskset >/dev/null 2>&1; then
  exec taskset -c "${pin_cpu}" "$@"
fi

exec "$@"
