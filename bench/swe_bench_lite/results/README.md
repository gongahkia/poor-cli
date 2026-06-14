# SWE-bench Lite results

Raw per-run results live here after `make bench-swe` completes.

Do commit:
- `summary.json`
- `predictions.jsonl`
- `task_results.jsonl`
- `evaluation_stdout.txt` and `evaluation_stderr.txt` when official evaluation ran
- top-level `*.{run_id}.json` official evaluation reports
- per-task `*.json`, `stdout.txt`, and `stderr.txt`

Do not commit:
- model API keys
- cloned task repositories
- Docker/image/task caches
- `.docker-config/`
- Docker build and per-instance logs under `logs/`
