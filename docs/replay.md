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

Verification checks event mirror integrity and CAS hashes, then emits a stable replay trace digest.

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
