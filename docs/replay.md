# Replay

Replay reconstructs orchestration state from the persisted event stream and artifacts.

## Store Layout

Run state lives under `.poor-cli/v6/`:

- `runs.sqlite3`: indexed run, task, event, agent, and artifact metadata.
- `cas/<sha256>`: global content-addressed artifacts.
- `runs/<run_id>/meta.json`: latest run metadata mirror.
- `runs/<run_id>/events.jsonl`: append-only event mirror.
- `runs/<run_id>/cas/<sha256>`: per-run artifact mirror.
- `runs/<run_id>/artifacts/`: deterministic human-facing plan, worker, review, verifier, and patch artifacts.

## Verify

```sh
poor-cli replay <run_id> --verify
```

Verification checks event mirror integrity and CAS hashes, then emits a stable replay trace digest:

```text
verify: PASS
network: no network used (socket attempts=0)
record: schema=poor-cli-record-v1 events=5 artifacts=4 bytes=1664
trace: sha256:<digest>
```

Text output includes a human verdict and a JSON verdict. The JSON uses `poor-cli-replay-verify-v1` and includes a `network` assertion. Verification installs a temporary socket guard and fails if replay verification touches network.

Replay verification checks the record; it does not re-run planners, providers, shell agents, tools, or validation commands. See [Record Schema](record-schema.md) for the deterministic boundary and migration policy.

## Offline

```sh
poor-cli --offline replay <run_id> --verify
```

Offline replay does not need planner, provider, or delegated-agent credentials for cached runs. Cache misses fail closed.

## Determinism Gate

```sh
python bench/replay_determinism_gate.py
```

The gate builds a temporary run, verifies it twice, and fails if replay verification is not byte-stable.

## Partial Replay

```sh
poor-cli replay <run_id> --from-event <event_id>
```

`--from-event` rebuilds state from an event window for debugging a later segment of a run.

## Diff And Fork

```sh
poor-cli runs diff <run_a> <run_b>
poor-cli runs diff <run_a> <run_b> --fail-on-change
poor-cli runs fork <run_id>
```

Diff compares route decisions, context packets, plan/task shape, artifact hashes, and repo-delta artifacts. Changes in those sections are classified as `behavior-changing`. Fork creates a new recorded run with a `run.fork` artifact pointing at the source run, so the next edit/re-run can be compared back with `runs diff`.

The regression loop is:

1. fork the source run with `poor-cli runs fork <run_id>`;
2. make the candidate edit and re-run the same goal;
3. compare source vs candidate with `poor-cli runs diff <source> <candidate> --fail-on-change`;
4. inspect changed route/context/plan/artifact/repo-delta sections before accepting the new behavior.
