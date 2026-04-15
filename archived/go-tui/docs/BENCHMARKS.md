# Benchmarks

## Go TUI Performance

Hardware: Apple M3, darwin/arm64. Command: `go test ./bench -run '^$' -bench . -benchtime=1x -count=1`.

### Targets

| Metric | Target | After | Status |
|---|---:|---:|---|
| Startup to first paint | <= 200 ms | 0.177 ms | pass |
| RSS steady-state | <= 50 MB | 21.05 MB | pass |
| Render latency per frame | <= 16 ms | 0.010 ms max | pass |
| Markdown streamer throughput | >= 30 MB/s | 75.59 MB/s | pass |
| CPU at 200 tok/s stream | <= 10% core | 1.575% core | pass |

### Before / After

| Benchmark | Before | After | Delta |
|---|---:|---:|---:|
| `BenchmarkMarkdownStreamer_Chunk` | 0.41 MB/s, 636.84 ms/op | 75.59 MB/s, 3.47 ms/op | 184x throughput |
| `BenchmarkChatView_AppendChunk` | 367.05 ms/op | 2.63 ms/op | 139x faster |
| `BenchmarkRenderer_TailSince` | 0.791 ms/op | 0.493 ms/op | 38% faster |
| `BenchmarkStartup_FirstPaint` | 0.125 ms first paint, 37.83 MB RSS | 0.177 ms first paint, 20.88 MB RSS | RSS down 45% |
| `BenchmarkE2E_200TokPerSec` | 16.94% core, 77.54 MB/op | 1.575% core, 2.21 MB/op | CPU down 91% |

### After Details

| Benchmark | ns/op | Throughput | allocs/op | Other |
|---|---:|---:|---:|---|
| `BenchmarkMarkdownStreamer_Chunk` | 3,472,541 | 75.59 MB/s | 41,478 | 4.65 MB/op |
| `BenchmarkChatView_AppendChunk` | 2,634,708 | n/a | 29,277 | 5.20 MB/op |
| `BenchmarkRenderer_TailSince` | 492,584 | n/a | 27 | 2.54 MB/op |
| `BenchmarkStartup_FirstPaint` | 182,000 | n/a | 137 | 0.177 ms first paint, 20.88 MB RSS |
| `BenchmarkE2E_200TokPerSec` | 1,010,636,667 | 197.9 tok/s | 27,232 | 0 dropped frames, 0.010 ms max frame, 21.05 MB RSS |

### Profiles

| Profile | Path |
|---|---|
| Before markdown CPU | `/tmp/poor-md.cpu` |
| Before chat CPU | `/tmp/poor-chat.cpu` |
| Before E2E CPU | `/tmp/poor-e2e.cpu` |
| After combined CPU | `/tmp/poor-bench-after.cpu` |
| After combined memory | `/tmp/poor-bench-after.mem` |

pprof changes made: removed full-render work from streamer drain, used cached assistant markdown segments during append, skipped Chroma in monochrome, reduced renderer segment coalescing churn, batched inline text parsing, and added monochrome ASCII render fast paths.

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
