# Launch

## Hero Copy

`poor-cli` is a verifiable run-record for coding agents.

It is built for developers who want AI coding sessions they can inspect, replay offline, benchmark, and defend with checked-in evidence.

Primary line:

> Verifiable AI coding runs from prompt to replay.

Support line:

> Capture the route, context, plan, agent I/O, artifacts, and benchmark evidence in one content-addressed store.

Prior-art posture:

- Claude Code Router shows that a router front-door is table stakes, not the differentiator.
- agent-replay, cagent, and Agent VCR show that replay, cassettes, and recording diffs are occupied.
- The launch claim is narrower: `poor-cli` ties route decision, context, DAG, agent I/O, and benchmark evidence into the same offline-verifiable record.

## Demo Slots

Phase 1:

- Show `poor-cli run` solving a fixture bug.
- Show `poor-cli inspect <run_id> --events --context`.
- Show `poor-cli --offline replay <run_id> --verify` with no provider credentials.

Phase 2:

- Show `poor-cli run --graph` on the same task.
- Show planner prompt bias toward `find_symbol`, `definition_of`, `callers_of`, `imports_of`, and `subgraph`.
- Show graph-vs-grep token/correctness row from `bench/results/graph-vs-grep-synthetic.json`.

Phase 3:

- Show vLLM or SGLang serving `Qwen/Qwen2.5-Coder-32B-Instruct` on Linux/CUDA.
- Show `poor-cli` using the local provider path.
- End with offline replay verification.
- Write the evidence file with `uv run --locked python bench/phase3_demo.py --write-template bench/results/phase3-demo.json --run-id <poor_cli_run_id> --store-dir <poor_cli_store_dir> --video-path bench/results/phase3-demo.mp4 --duration-seconds 60 --internet-disabled --network-probe-exit-code <nonzero> --local-gpu --gpu-probe-exit-code 0 --gpu-probe-output <nvidia-smi-gpu-name> --graph-tools-visible --offline-replay-verified`.
- Validate the evidence with `uv run --locked python bench/phase3_demo.py --evidence bench/results/phase3-demo.json`.

## Publication Checklist

- README points at `TODO.md`.
- MkDocs builds with `mkdocs build --strict`.
- `BENCHMARKS.md` links checked-in result rows.
- Phase 1 acceptance snapshot is green.
- Phase 2 graph-mode result row is present before the graph-mode launch.
- Phase 3 readiness snapshot is green on the target Linux/CUDA workstation before the local-first launch.
- Phase 3 screencast evidence passes `bench/phase3_demo.py`.
