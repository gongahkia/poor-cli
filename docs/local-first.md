# Local First

Phase 3 targets Linux/CUDA local model runs through vLLM, SGLang, or Ollama.

## Setup

```sh
scripts/setup-linux-cuda.sh --yes --engine vllm --model Qwen/Qwen2.5-Coder-32B-Instruct
```

The setup script creates:

- `.poor-cli/local-cuda-venv/`
- `.poor-cli/local-cuda.env`
- `.poor-cli/local-cuda-run.sh`

It requires Linux and a working `nvidia-smi --query-gpu=name --format=csv,noheader` GPU query by default. For CI or syntax validation only, pass `--skip-cuda-check` and set `POOR_CLI_ALLOW_NON_LINUX=1`.
The generated `.poor-cli/local-cuda.env` exports the provider, model, local Python, local venv, and base URL variables used by the `local` agent path and readiness checks.
The closeout path also requires a running Docker daemon for official SWE-bench evaluation.

## Engines

```sh
scripts/setup-linux-cuda.sh --yes --engine vllm
scripts/setup-linux-cuda.sh --yes --engine sglang
scripts/setup-linux-cuda.sh --yes --engine ollama --skip-engine-install
scripts/setup-linux-cuda.sh --yes --engine vllm --python python3.12
```

The script installs `vllm` or `sglang[all]` into the local venv when selected. Ollama is expected to be installed as a system service or binary.

## poor-cli Agent

The setup env exposes a provider-backed delegated agent named `local`:

```sh
set -a; source .poor-cli/local-cuda.env; set +a
poor-cli run "inspect this bug" --agents local --yes
uv run --locked --extra bench python bench/swe_bench_lite/run.py --graph --agent local --provider "$POOR_CLI_PROVIDER" --model "$POOR_CLI_MODEL" --local-base-url "$POOR_CLI_LOCAL_BASE_URL" --confirm-cost --no-evaluate
```

`POOR_CLI_PROVIDER` must be `vllm`, `sglang`, or `ollama`, and `POOR_CLI_MODEL` must be set. `POOR_CLI_LOCAL_BASE_URL` selects the local server endpoint; vLLM/SGLang accept either the server origin or its `/v1` API base. `POOR_CLI_LOCAL_VENV` points readiness checks at the venv where vLLM or SGLang was installed.

## Cache Controls

The setup script enables provider-native prefix caching by default where the engine exposes it:

```sh
scripts/setup-linux-cuda.sh --yes --engine vllm --prefix-cache-hash-algo sha256 --kv-cache-dtype fp8_e5m2
scripts/setup-linux-cuda.sh --yes --engine sglang --kv-cache-dtype fp8_e5m2
scripts/setup-linux-cuda.sh --yes --engine vllm --no-prefix-cache
scripts/setup-linux-cuda.sh --yes --engine sglang --no-prefix-cache
```

For vLLM, `--prefix-cache` writes `--enable-prefix-caching` and `--prefix-caching-hash-algo` into `.poor-cli/local-cuda-run.sh`; `--no-prefix-cache` writes `--no-enable-prefix-caching`.
For SGLang, prefix cache is the radix cache path; `--no-prefix-cache` writes `--disable-radix-cache`.
For both engines, `--kv-cache-dtype` is passed through when set to anything other than `auto`.

## Replay

Record/replay remains the control plane. A local model run should still produce a normal run store, and `poor-cli --offline replay <run_id> --verify` should verify without credentials.

## Phase 3 Benchmark Gate

```sh
scripts/phase3-closeout-linux-cuda.sh --yes --start-server --run-id swe10-local-YYYYMMDDTHHMMSSZ \
  --stop-server-on-exit --write-demo-evidence --demo-video-path bench/results/phase3-demo.mp4 --demo-duration-seconds 60 \
  --demo-internet-disabled --demo-local-gpu --demo-graph-tools-visible --demo-offline-replay-verified
uv run --locked python bench/phase3_demo.py --evidence bench/results/phase3-demo.json
uv run --locked python bench/phase3_acceptance.py --output bench/results/phase3-acceptance.json
uv run --locked python bench/phase3_closeout.py --output bench/results/phase3-closeout.json
uv run --locked python bench/phase3_local_benchmark.py --output bench/results/phase3-local-benchmark-plan.json
uv run --locked python bench/phase3_local_benchmark.py --summary bench/swe_bench_lite/results/swe10-local-YYYYMMDDTHHMMSSZ/summary.json
```

The verifier is the local-mode closeout gate for the pivot audit. It rejects non-local providers, non-local endpoints, non-graph runs, missing or mismatched run artifacts, partial replay verification, incomplete official eval, and pass rates below 50% of the checked-in Anthropic 10-task row.
With `--start-server`, the closeout runner starts `.poor-cli/local-cuda-run.sh` in the background, waits for the local provider health endpoint, and writes `.poor-cli/phase3-closeout-server.pid`. Add `--stop-server-on-exit` when the closeout command should stop the server it started.
When writing demo evidence from a SWE-bench run, the closeout runner derives the replay run id and store dir from the first replay-verified task in `task_results.jsonl`.
It also records a failed internet probe and an `nvidia-smi` GPU probe before writing accepted screencast evidence.
