#!/usr/bin/env bash
set -euo pipefail

BASE_SHA="${BASE_SHA:-}"
if [[ -z "$BASE_SHA" ]]; then
  echo "BASE_SHA must be set to the pull request base commit SHA." >&2
  exit 1
fi

REGRESSION_THRESHOLD_PCT="${REGRESSION_THRESHOLD_PCT:-12}"
SAMPLE_SIZE="${SAMPLE_SIZE:-20}"
MEASUREMENT_TIME="${MEASUREMENT_TIME:-2}"

ROOT_DIR="$(git rev-parse --show-toplevel)"
cd "$ROOT_DIR"

HEAD_SHA="$(git rev-parse HEAD)"
OUTPUT_DIR="$ROOT_DIR/.perf-gate"
mkdir -p "$OUTPUT_DIR"

cleanup() {
  git checkout --quiet "$HEAD_SHA" || true
}
trap cleanup EXIT

run_bench_for_sha() {
  local label="$1"
  local sha="$2"

  echo "Running benchmarks for $label ($sha)"
  git checkout --quiet "$sha"
}

run_bench_for_sha base "$BASE_SHA"
rm -rf target/criterion
cargo bench -p wok --bench large_workspace -- \
  --sample-size "$SAMPLE_SIZE" \
  --measurement-time "$MEASUREMENT_TIME" \
  --save-baseline ci_base \
  --noplot \
  --quiet

run_bench_for_sha head "$HEAD_SHA"
cargo bench -p wok --bench large_workspace -- \
  --sample-size "$SAMPLE_SIZE" \
  --measurement-time "$MEASUREMENT_TIME" \
  --baseline ci_base \
  --noplot \
  --quiet

export OUTPUT_DIR HEAD_SHA BASE_SHA REGRESSION_THRESHOLD_PCT SAMPLE_SIZE MEASUREMENT_TIME

python3 - <<'PY'
import json
import os
from pathlib import Path

output_dir = Path(os.environ["OUTPUT_DIR"])
base_sha = os.environ["BASE_SHA"]
head_sha = os.environ["HEAD_SHA"]
threshold_pct = float(os.environ["REGRESSION_THRESHOLD_PCT"])
sample_size = os.environ["SAMPLE_SIZE"]
measurement_time = os.environ["MEASUREMENT_TIME"]

specs = [
    ("global_search", "Global Search", "large_workspace_global_search/query_error"),
    ("block_query", "Block Query Filter", "large_workspace_block_query/filter_timeout"),
    ("command_search", "Command Search", "large_workspace_command_search/query_cargo_test"),
]

rows = []
for bench_id, display_name, criterion_path in specs:
    base_path = Path("target/criterion") / criterion_path / "ci_base" / "estimates.json"
    head_path = Path("target/criterion") / criterion_path / "new" / "estimates.json"
    change_path = Path("target/criterion") / criterion_path / "change" / "estimates.json"

    if not base_path.exists():
        raise SystemExit(f"missing benchmark baseline: {base_path}")
    if not head_path.exists():
        raise SystemExit(f"missing benchmark head estimate: {head_path}")
    if not change_path.exists():
        raise SystemExit(f"missing benchmark change estimate: {change_path}")

    base_json = json.loads(base_path.read_text())
    head_json = json.loads(head_path.read_text())
    change_json = json.loads(change_path.read_text())

    base_median_ns = float(base_json["median"]["point_estimate"])
    head_median_ns = float(head_json["median"]["point_estimate"])

    change_point_pct = float(change_json["median"]["point_estimate"]) * 100.0
    change_lower_pct = float(change_json["median"]["confidence_interval"]["lower_bound"]) * 100.0
    change_upper_pct = float(change_json["median"]["confidence_interval"]["upper_bound"]) * 100.0

    regressed = change_lower_pct > threshold_pct

    rows.append(
        {
            "id": bench_id,
            "name": display_name,
            "base_median_ns": base_median_ns,
            "head_median_ns": head_median_ns,
            "change_point_pct": change_point_pct,
            "change_lower_pct": change_lower_pct,
            "change_upper_pct": change_upper_pct,
            "regressed": regressed,
        }
    )

regressions = [row for row in rows if row["regressed"]]

summary_lines = [
    "## Performance Gate",
    "",
    f"- Base SHA: `{base_sha}`",
    f"- Head SHA: `{head_sha}`",
    f"- Threshold: `{threshold_pct:.1f}%` median regression",
    f"- Criterion settings: sample_size=`{sample_size}`, measurement_time=`{measurement_time}s`",
    "",
    "| Benchmark | Base Median (ms) | Head Median (ms) | Delta | Status |",
    "| --- | ---: | ---: | ---: | --- |",
]

for row in rows:
    delta = row["change_point_pct"]
    ci = f"[{row['change_lower_pct']:+.2f}%, {row['change_upper_pct']:+.2f}%]"
    status = "FAIL" if row["regressed"] else "PASS"
    summary_lines.append(
        f"| {row['name']} | {row['base_median_ns'] / 1_000_000:.3f} | {row['head_median_ns'] / 1_000_000:.3f} | {delta:+.2f}% (95% CI {ci}) | {status} |"
    )

if regressions:
    summary_lines.extend(
        [
            "",
            f"Result: **FAILED** ({len(regressions)} benchmark(s) regressed above threshold).",
        ]
    )
else:
    summary_lines.extend(
        [
            "",
            "Result: **PASSED** (no benchmark exceeded regression threshold).",
        ]
    )

summary_text = "\n".join(summary_lines) + "\n"

result_payload = {
    "base_sha": base_sha,
    "head_sha": head_sha,
    "threshold_pct": threshold_pct,
    "sample_size": int(sample_size),
    "measurement_time_seconds": int(measurement_time),
    "benchmarks": rows,
    "failed": bool(regressions),
}

(output_dir / "perf-gate-summary.md").write_text(summary_text)
(output_dir / "perf-gate-results.json").write_text(json.dumps(result_payload, indent=2))

print(summary_text)

if regressions:
    raise SystemExit(1)
PY

if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
  cat "$OUTPUT_DIR/perf-gate-summary.md" >> "$GITHUB_STEP_SUMMARY"
fi
