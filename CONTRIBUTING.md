# Contributing

## Line Budgets

Run `make lint-sizes` before opening a PR. CI and pre-commit enforce these Python line budgets:

| File | Limit |
|---|---:|
| `poor_cli/core.py` | 1,000 |
| `poor_cli/server/runtime.py` | 5,600 until Phase 10B partitions handlers |
| `poor_cli/config.py` | 1,500 |
| `poor_cli/tools_async.py` | 4,300 until its split PRD lands |
| `poor_cli/multiplayer.py` | 2,150 until PRD 063 resolves commit/cut |
| `poor_cli/core_turn_lifecycle.py` | 2,700 until the lifecycle slice is narrowed |
| Any other non-test, non-generated, non-vendored `.py` file | 2,000 |

Budget errors use `path current/limit (+delta)`, for example `poor_cli/core.py 1124/1000 (+124)`.
