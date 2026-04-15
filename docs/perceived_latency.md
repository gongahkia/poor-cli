# Perceived Latency

Hardware: Apple M3, darwin/arm64.

Command:

```console
$ go test ./bench -run TestPerceivedLatencyTargets -count=1 -v
$ go test ./bench -run '^$' -bench 'Benchmark(ChatView_AppendChunk|Renderer_TailSince|Startup_FirstPaint|E2E_200TokPerSec)' -benchtime=1x -count=1
```

## Targets

| Metric | Target | After | Status |
|---|---:|---:|---|
| Keystroke to echo | <= 8 ms | 0.084 ms | pass |
| First stream byte to visible text | <= 16 ms | 0.142 ms | pass |
| Render frame at 200 tok/s | <= 8 ms | 0.001 ms p95 | pass |
| Render cadence | 60 Hz | 60.0 Hz | pass |
| Splash to first paint | <= 150 ms | 0.122 ms | pass |

## Before / After

| Check | Before | After |
|---|---:|---:|
| `BenchmarkChatView_AppendChunk` | 2.348 ms/op, 5.31 MB/op, 29,296 allocs/op | 2.008 ms/op, 5.04 MB/op, 27,410 allocs/op |
| `BenchmarkRenderer_TailSince` | 0.304 ms/op, 2.54 MB/op, 26 allocs/op | 0.295 ms/op, 2.54 MB/op, 26 allocs/op |
| `BenchmarkStartup_FirstPaint` | 0.164 ms first paint, 21.17 MB RSS | 0.166 ms first paint, 21.28 MB RSS |
| `BenchmarkE2E_200TokPerSec` | 1.720% core, 2.22 MB/op, 27,237 allocs/op | 2.55-3.32% core, 0.69 MB/op, ~6,450 allocs/op |

## Profiles

| Profile | Path |
|---|---|
| Before chat CPU flamegraph | `/tmp/poor-perceived-before.svg` |
| Before tail CPU flamegraph | `/tmp/poor-tail-before.svg` |
| After chat CPU flamegraph | `/tmp/poor-perceived-after.svg` |
| After tail CPU flamegraph | `/tmp/poor-tail-after.svg` |
| Before chat CPU profile | `/tmp/poor-perceived-before.cpu` |
| After chat CPU profile | `/tmp/poor-perceived-after.cpu` |
| After chat alloc profile | `/tmp/poor-perceived-after.mem` |

## Notes

- `bench/perceived_latency_test.go` drives Bubbletea key/update/view paths and the streaming chat renderer at 50, 100, and 200 tok/s.
- Trace logging is enabled with `GOCLI_POOR_TRACE=1` and writes JSONL to `$XDG_STATE_HOME/gocli-poor/trace.jsonl`.
- Markdown tail repaint remains segment-based: when `TailSince` produces segments, chat appends only those rendered tail lines. Empty-tail chunks fall back to full render to preserve the current streaming visual behavior.
- `state.Store` now stamps revisions and avoids one subscriber clone on the common single-subscriber path; append-chunk/thinking reducers use copy-on-write message edits instead of cloning every message body.
