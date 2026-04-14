# Benchmarks

## SWE-bench Lite

**Status:** harness implemented; no citable pass@1 is published until the first full run is completed and committed.

**Benchmark:** SWE-bench Lite, 300 tasks from `princeton-nlp/SWE-bench_Lite`.
**Dataset revision:** `6ec7bb89b9342f664a54a6e0a6ea6501d3437cc2`.
**Harness deps:** `swebench==4.1.0`, `datasets==4.8.4`, `tqdm==4.67.3`.
**Default model:** `anthropic/claude-sonnet-4-20250514`.
**Seed:** `0`.
**Agent command:** `poor-cli exec --prompt "$problem_statement" --output-format json`.
**Config deviations:** benchmark runner defaults to `--permission-mode acceptEdits`, `--sandbox-preset workspace-write`, and `--auto-approve` so headless task repos can be edited without interactive prompts.
**Benchmark-specific tuning:** none. The prompt is exactly the SWE-bench `problem_statement`; no per-task prompts, heuristics, or cherry-picking are shipped.

### Current Published Result

| Run | Commit | Model | Tasks | pass@1 | Mean cost/task | Mean wall time/task | p50 / p95 wall time | Raw results |
|---|---|---|---:|---:|---:|---:|---:|---|
| pending | pending | `anthropic/claude-sonnet-4-20250514` | 300 | not run | not run | not run | not run | pending |

Do not cite a score until this table points to a committed `bench/swe_bench_lite/results/<run-id>/summary.json`.

### Cost Story

SWE-bench spend is reported as total USD and mean USD/task from `poor-cli` token telemetry. Pair this with the Savings Dashboard (`/savings`, `:PoorCLISavingsDashboard`) when presenting cost: benchmark cost is actual spend; Savings Dashboard values are estimated avoided spend by source.

### Reproduce

```console
$ python -m pip install -r bench/swe_bench_lite/requirements.txt
$ make bench-swe ARGS="--provider anthropic --model claude-sonnet-4-20250514"
```

Smoke run:

```console
$ make bench-swe ARGS="--limit 1 --no-evaluate"
```

Outputs:
- `bench/swe_bench_lite/results/<run-id>/environment.json`
- `bench/swe_bench_lite/results/<run-id>/task_results.jsonl`
- `bench/swe_bench_lite/results/<run-id>/predictions.jsonl`
- `bench/swe_bench_lite/results/<run-id>/<instance_id>/result.json`
- `bench/swe_bench_lite/results/<run-id>/<instance_id>/stdout.txt`
- `bench/swe_bench_lite/results/<run-id>/<instance_id>/stderr.txt`
- `bench/swe_bench_lite/results/<run-id>/summary.json`
- `bench/swe_bench_lite/results/<run-id>/evaluation_stdout.txt`
- `bench/swe_bench_lite/results/<run-id>/evaluation_stderr.txt`

The official SWE-bench evaluator writes its own `results.json`; the runner records the discovered path inside `summary.json`.

### Landing Page

No standalone site/landing page exists in this repository. `README.md` is the project landing surface and links this page.
