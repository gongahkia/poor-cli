# Record Schema

Current run-record schema: `poor-cli-record-v1`.

`poor-cli` records enough state to answer what was asked, what route/context/plan the agent received, what ran, what artifacts were produced, and whether the record mirrors still verify offline.

## Layout

Run records live under `.poor-cli/v6/`:

- `runs.sqlite3`: indexed metadata for runs, tasks, events, agents, and artifacts.
- `runs/<run_id>/meta.json`: latest run row mirror, including `schema_version`.
- `runs/<run_id>/events.jsonl`: append-only event mirror.
- `cas/<sha256>`: global content-addressed artifact payloads.
- `runs/<run_id>/cas/<sha256>`: per-run CAS mirror used by replay verification.
- `runs/<run_id>/artifacts/`: human-facing deterministic files such as `PLAN.md`, `RESULT.md`, `PATCH.diff`, `REVIEW.json`, and `VERIFY.json`.

## Core Shape

The stable record shape is:

```text
run -> route -> context -> plan/tasks -> agent I/O -> artifacts -> verify
```

Required run fields:

- `run_id`
- `schema_version`
- `created_at`
- `repo_path`
- `git_commit_start`
- `user_goal`
- `mode`
- `budget`
- `plan_id`
- `status`
- `final_summary`

Required replay-critical event fields:

- `event_id`
- `run_id`
- `task_id`
- `type`
- `created_at`
- `payload`

Required replay-critical artifact fields:

- `artifact_id`
- `run_id`
- `task_id`
- `kind`
- `sha256`
- `size`
- `media_type`
- `created_at`
- `path`

## Answerability Matrix

| Question | Evidence |
| --- | --- |
| What did the user ask? | `runs.user_goal`, `run.created.payload.goal`, `poor-cli inspect <run_id> --json` |
| What did the router classify? | `route.decision`, `route.selected`, `route.policy.selected`, and shim `route.preflight` artifacts/events |
| Which backend was chosen and why? | Route decision provider/model/profile fields, task agent assignment, fallback fields, and `agents.detected` |
| What context did the agent receive? | `context.packet`, `graph.context`, `agent.input`, and `handoff.packet` artifacts |
| What plan/tasks were created? | `PLAN.md`, `PLAN.json`, task rows, and task lifecycle events |
| Which tasks ran/skipped/failed/cancelled? | Task rows plus `task.*`, `agent.completed`, `agent.failed`, and `run.*` events |
| What artifacts were produced? | Artifact rows, global CAS, per-run CAS mirrors, and `runs/<run_id>/artifacts/` |
| What changed in the repo? | Worker patch/changed-file artifacts and `PATCH.diff` when a run produces a repo delta; the live worktree `git diff` remains the final filesystem delta |
| Can the run be replayed without API/network? | `poor-cli replay <run_id> --verify` and its `network_assertion.attempts == 0` JSON verdict |
| Which claims are backed by checked-in evidence? | `bench/results/*.json`, `bench/claims_gate.py`, `bench/release_gate.py`, and docs that cite those checked-in evidence files |

## Verification Semantics

`poor-cli replay <run_id> --verify` must:

- verify the run event mirror matches SQLite event ids and event count;
- verify every artifact payload exists in global CAS;
- verify every artifact payload has a matching per-run CAS mirror;
- emit `poor-cli-replay-verify-v1` JSON with `verified`, `record_schema_version`, counts, byte size, trace digest, deterministic scope, and network assertion;
- install a temporary socket guard and fail if replay verification touches network;
- exit non-zero on any mismatch or network attempt.

## Deterministic Boundary

Deterministic:

- run metadata reconstruction;
- event order and task state reconstruction;
- artifact hash verification;
- per-run CAS mirror verification;
- replay trace digest.

Not deterministic:

- planner calls;
- provider calls;
- shell-agent execution;
- tool execution;
- validation command execution.

Those systems are recorded as inputs, outputs, events, and artifacts. Replay verification checks the record; it does not re-run the original agent.

## Migration Policy

New records use the current schema version. Older records keep their original `schema_version` and must remain verifiable unless a migration note explicitly marks an unsupported format.

Migration notes must state:

- old schema version;
- new schema version;
- changed fields;
- whether replay verification stays compatible;
- required one-time migration command, if any.
