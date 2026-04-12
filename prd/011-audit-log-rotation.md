# PRD 011: Audit log rotation, archival, and export

- **Wave:** 1
- **Status:** ready
- **Owner (human):** @gongahkia
- **Estimated effort:** small (1–2d)
- **Blocks:** —
- **Blocked by:** —
- **Files it mutates:**
  - `poor_cli/audit_log.py`
- **New files it adds:**
  - `tests/test_audit_log_rotation.py`

## 1. Problem

`.poor-cli/runs.db` (or whichever SQLite file backs the audit log) grows unbounded. In a year of daily use it's gigabytes. No rotation, no archival policy, no export. LEARNING.md §2.3: "Audit log is single SQLite; no rotation / archival."

## 2. Current state

`audit_log.py` writes rows to an append-only SQLite table. Rows are never deleted. No export interface.

## 3. Goal & non-goals

**Goal:** the audit DB has a size cap with a rotation policy, an export-to-JSONL command, and a scheduled archival that moves old rows out to `.poor-cli/audit/archive/YYYY-MM.jsonl.gz` before trimming them from the live DB.

**Non-goals:**
- Do not change the audit schema.
- Do not centralize to a remote sink.

## 4. Design

### 4.1 Policy

Configurable (default in parens):
- `audit.max_rows_live` (100,000)
- `audit.max_age_days_live` (90)
- `audit.archive_chunk_size` (10,000)
- `audit.archive_dir` (`.poor-cli/audit/archive/`)

Background task (existing scheduler or a small asyncio task) checks on a 1-hour cadence. When either cap is exceeded, oldest rows are streamed to a gzipped JSONL file and deleted from the live DB in a single transaction per chunk.

### 4.2 Export CLI

`poor-cli audit export --from 2026-01-01 --to 2026-02-01 --out events.jsonl` — streams matching rows to stdout or file. Implement as an RPC method + a thin CLI wrapper.

### 4.3 Archive format

One file per month, gzipped JSONL. Schema = audit row schema. Each line a full record so downstream tooling can process naively.

## 5. Files to create / modify / delete

**Create**
- `tests/test_audit_log_rotation.py`

**Modify**
- `poor_cli/audit_log.py` — add `rotate()`, `archive()`, `export_range()`.
- CLI entry (likely in `poor_cli/cli/`) — add `poor-cli audit ...` command.
- Scheduler hook — every 1 hour, call `rotate_if_needed()`.

## 6. Implementation plan

1. Add `rotate_if_needed()` method with size-based and age-based triggers.
2. Add `archive(chunk_size)` streamer that writes gzipped JSONL and deletes rows.
3. Add `export_range(start, end, dest)`.
4. Hook into scheduler.
5. Add CLI subcommand.
6. Tests with a synthetic DB of 200k rows: rotate, verify archive file, verify DB shrinks.
7. `make lint && make test`.

## 7. Testing & acceptance criteria

- `test_rotation_respects_max_rows`
- `test_rotation_respects_max_age`
- `test_archive_file_roundtrips_with_export`
- `test_rotation_is_atomic_on_failure`

**Done criterion**
- [ ] Rotation ships and is exercised by the scheduler.
- [ ] Archive files validate as gzip+JSONL.
- [ ] Export command works.

## 8. Rollback / risk

Low. Worst case: a rotation fails mid-transaction → rollback in SQLite. Cap rotation runtime to avoid long UI stalls.

## 9. Out-of-scope & boundary

- 🚫 Do not change audit row schema.
- 🚫 Do not introduce remote sinks.

## 10. Related PRDs & references

- LEARNING.md §2.3.
- PRD 003 (schema versioning) adds `meta.schema_version` to this DB.
