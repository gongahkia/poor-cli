# PROPOSAL F — Harness Robustness for Mutating Tool Calls

> **Target:** poor-cli v6.4 / backend-only (Python).
> **Depends on:** Phases A / B / C landed. Independent of D / E — lands in parallel.
> **Estimated effort:** 2 engineer days.

---

## 1. Philosophical bearings

**Never catastrophic.** The harness has exclusive tools (`git.commit`,
`git.push`, `deploy.run`, `hunks.reset`, etc.) that mutate state. A misbehaving
agent + a too-eager retry loop + no idempotency = double-commits, double-pushes,
or worse. Robustness here is the difference between poor-cli as a production
tool and poor-cli as a research toy.

**Agent-centric.** The agent drives mutation. That means the harness must
protect the agent from its own mistakes — not by refusing actions, but by
making sure the second retry of an already-committed commit doesn't commit
again, that the tenth consecutive broken tool stops being called, and that
a failed mutation can roll back without human intervention.

**Cheap.** Every safety net must cost near-zero tokens and near-zero time on
the happy path. If robustness makes routine calls sluggish, we're doing it
wrong.

**Not a permission system.** PROPOSAL-F does not replace or compete with
trust/permission rules (Phase-C T7). Permissions ask "is this agent allowed
to do this action?" F asks "is this action safe to actually execute *right
now*?" Different layer.

## 2. Anti-scope-creep fences

- **No distributed transactions.** In-process only. If the user runs two
  poor-cli sessions concurrently on the same repo, they conflict the same
  way they always did.
- **No undo beyond what git or our checkpoint system already provides.**
  We don't build a new snapshot primitive; we reuse `poor_cli/checkpoint.py`.
- **No external service integrations.** No Sentry, no cloud state, no
  remote locking.
- **No per-user auth on tools.** That's the trust center's job.
- **No arbitrary "global circuit breaker" that cuts off all tools.** Per-tool
  only — one broken tool must not block unrelated ones.

## 3. End state (definition of success)

Four features, each independently landable:

| Feature | Purpose |
|---|---|
| F1 Circuit breaker | Stop calling a tool that's failing ≥X/Y recent calls until cool-off |
| F2 Idempotency keys | Allow exclusive tools to dedupe retries within a session |
| F3 Auto-checkpoint | Snapshot affected files before every exclusive tool; restore on error |
| F4 Rate limits | Per-tool request/minute cap (agent-facing error when exceeded) |

**Hard invariants:**

1. **F1:** After 5 consecutive failures of `git.push` within 60s, the 6th
   dispatch returns immediately with `metadata.circuit_open = True`, does
   NOT invoke the handler, and after 30s the circuit half-opens and one
   probe attempt is allowed.
2. **F2:** Dispatching `git.commit` with `idempotency_key="abc"` twice in
   the same session runs the handler exactly once; the second call returns
   the cached result with `metadata.idempotent_replay = True`.
3. **F3:** On a `git.commit` tool error, the repo state (for tracked files
   listed in args) is restored from the auto-checkpoint taken pre-dispatch.
4. **F3 correctness:** Auto-checkpoint is skipped when `checkpointing = false`
   in trust config.
5. **F4:** Calling `git.push` 4 times in < 60s with `max_per_minute=3`
   returns the 4th call immediately with `metadata.rate_limited = True`.
6. **No happy-path latency regression.** Handler wall time for a
   healthy+unique+under-rate call is within 5% of the pre-F dispatch path
   (measured via benchmark).

**Test coverage:** ≥ 18 pytest cases spanning all four features.

## 4. Feature design

### 4.1 F1 — Circuit breaker

**Where:** new module `poor_cli/tool_circuit.py`; called from
`tool_dispatcher.dispatch_one` immediately after the unknown-tool check.

**Rule:** per-tool circuit state = one of `{closed, open, half_open}`:

- `closed` (normal): dispatch runs. On failure, increment a rolling failure
  count within `window_s` (default 60s). If count ≥ `threshold` (default 5),
  flip to `open`.
- `open`: dispatch immediately short-circuits with `ToolResult.error(...)`
  (`metadata.circuit_open = True`). After `cooldown_s` (default 30s), flip
  to `half_open`.
- `half_open`: next dispatch is allowed as a probe. If it succeeds, back to
  `closed`; if it fails, back to `open` for another cooldown.

**Per-tool tuning:** extend `ToolSpec`:

```python
circuit_threshold: int = 5          # failures to trip
circuit_window_s: float = 60.0      # rolling window
circuit_cooldown_s: float = 30.0    # open → half_open
circuit_disabled: bool = False      # opt-out per tool
```

Pure introspection tools (`meta.*`, `fs.browse`, `git.status`) can set
`circuit_disabled = True` — no point throttling read-only tools.

**Signal source:** the existing `tool_health` module already records
per-tool failure counts. `tool_circuit` reads from it rather than maintaining
a parallel state machine. Single source of truth.

**Visibility:** add circuit state to `meta.health` output (PROPOSAL D).
User-visible via `:PoorCLIDiag` tool health drill (Phase C T9).

### 4.2 F2 — Idempotency keys for exclusive tools

**Where:** `poor_cli/tool_idempotency.py` (new); called from
`tool_dispatcher._dispatch_once` before the handler invocation.

**Contract:**

- Tool schemas for exclusive tools gain an OPTIONAL `idempotency_key` arg
  (string, UUIDv4 recommended). Not required for backward compat — if the
  agent doesn't send one, we're in the current unguarded behavior.
- When the dispatcher sees `idempotency_key` in args:
  1. Key the session-scoped `IdempotencyStore` by `(tool, key)`.
  2. If entry exists, return the cached `ToolResult` with
     `metadata.idempotent_replay = True`.
  3. Otherwise, run the handler. On success, store the result.
  4. On `TransientError` → don't store; retry logic handles it.
  5. On `ToolError` → store with `is_error=True` so retries don't re-trigger
     the failure path.

**Scope:** session only. Cross-session deduping would require persistent
storage, which we don't want (see §2).

**Schema update:** add `idempotency_key` optional field to every exclusive
tool's schema. Programmatic: iterate tools in registry, if `spec.exclusive`,
ensure schema's properties include:

```json
"idempotency_key": {
  "type": "string",
  "pattern": "^[A-Za-z0-9_-]{8,64}$",
  "description": "Optional deduplication key. Reuse across retries to prevent double execution."
}
```

**System prompt hint:** add a line in the tool manifest for exclusive tools:
"This is an exclusive/mutating tool. For idempotent retries, reuse an
`idempotency_key` UUID."

### 4.3 F3 — Auto-checkpoint before exclusive tools

**Where:** hook in `tool_dispatcher._dispatch_once` before the handler
invocation, for any tool where `spec.exclusive and spec.auto_checkpoint`.

**Default `auto_checkpoint`:** true for exclusive tools; overridable per-tool.

**Flow:**

1. Pre-dispatch: extract candidate paths from args (heuristic: same list
   the SessionRecorder uses — `file`, `files`, `path`, `paths`, etc.).
   For tools without path args (e.g. `git.push`), skip — can't snapshot.
2. Call `poor_cli.checkpoint.create(paths=<extracted>, reason=f"auto before {tool}")`.
   Store checkpoint id in local var.
3. Dispatch handler.
4. On `is_error` result AND `spec.auto_rollback = True` (default false —
   rollback is opt-in; checkpoint is opt-out default):
   call `poor_cli.checkpoint.restore(checkpoint_id)`. Set
   `metadata.rolled_back = True`.
5. On success: leave the checkpoint in place. The user's normal
   `:PoorCLIReview checkpoint` flow manages retention.

**Config gate:** respect existing trust config `checkpointing = false` —
skip entirely.

**Rationale for rollback being opt-in:** rolling back implicitly can
surprise users (e.g. agent's `git.commit` "failed" because nothing was
staged — rolling back some other file would be wrong). We wire the plumbing
and flip specific tools to `auto_rollback = True` only after verifying
safety: initially `hunks.reset`, `fs.write` (from future PROPOSAL-D follow-up).

### 4.4 F4 — Per-tool rate limits

**Where:** `poor_cli/tool_rate_limit.py` (new); consulted in
`tool_dispatcher._dispatch_once`.

**Contract:**

- Extend `ToolSpec`: `max_per_minute: int | None = None` (default: unlimited).
- Rate limiter keeps a per-session-per-tool deque of timestamps.
- Before dispatch: purge timestamps older than 60s; if deque length ≥
  `max_per_minute`, return `ToolResult.error(...)` with
  `metadata.rate_limited = True` and `retry_after_s = <next available>`.
  Do NOT call handler.

**Default per tool:**

- `git.push` → `max_per_minute = 3`
- `deploy.run` → `max_per_minute = 2`
- `task.run` → `max_per_minute = 10`
- Everything else → unlimited

**Agent feedback:** the error message tells the agent exactly when it can
retry (not a general "try later").

**User opt-out:** global config flag `tools.rate_limits = false` disables.

## 5. Files expected to be touched

```
poor_cli/tool_circuit.py               NEW (~150 LOC)
poor_cli/tool_idempotency.py           NEW (~100 LOC)
poor_cli/tool_rate_limit.py            NEW (~90 LOC)
poor_cli/tool_dispatcher.py            MOD (~80 LOC: pre-dispatch checks,
                                            post-dispatch checkpoint hooks)
poor_cli/tools/_registry.py            MOD (~20 LOC: new fields on ToolSpec)
poor_cli/tools/git.py                  MOD (~10 LOC: max_per_minute on push)
poor_cli/tools/deploy.py               MOD (~5 LOC: max_per_minute on run)
poor_cli/tool_health.py                MOD (~15 LOC: expose `is_circuit_open(tool)`)
poor_cli/tools/meta.py                 MOD (~10 LOC: surface circuit state in meta.health)
poor_cli/config.py                     MOD (~15 LOC: new feature flags)
tests/test_tool_circuit.py             NEW (~120 LOC, ~5 cases)
tests/test_tool_idempotency.py         NEW (~100 LOC, ~5 cases)
tests/test_tool_rate_limit.py          NEW (~80 LOC, ~4 cases)
tests/test_tool_auto_checkpoint.py     NEW (~120 LOC, ~4 cases)
```

## 6. Test specification

### F1 Circuit

```python
def test_circuit_opens_after_threshold():
    # Register a tool with circuit_threshold=3. 3 consecutive failures → 4th call
    # returns is_error without invoking handler. metadata.circuit_open=True.

def test_circuit_does_not_open_for_disabled_tools():
    # circuit_disabled=True → never opens.

def test_circuit_half_opens_after_cooldown():
    # Trip circuit; advance time; next call is allowed.

def test_circuit_half_open_success_closes():
    # After cooldown, one success → circuit closed, further failures count fresh.

def test_circuit_half_open_failure_reopens():
    # After cooldown, one failure → circuit re-opens for another cooldown.
```

### F2 Idempotency

```python
def test_idempotency_replays_cached_result():
    # Two calls, same key → handler invoked once.

def test_different_keys_run_independently():
    # Same tool, different keys → two handler invocations.

def test_idempotency_caches_error_result_too():
    # Handler raises ToolError; second call with same key returns cached error.

def test_transient_error_not_cached():
    # Handler raises TransientError; second call with same key re-runs.

def test_no_key_means_no_dedup():
    # Two calls without idempotency_key → two invocations.
```

### F3 Auto-checkpoint

```python
def test_checkpoint_created_before_exclusive_tool():
    # Register a dummy exclusive tool; dispatch; verify checkpoint.create called
    # with extracted paths.

def test_rollback_on_error_when_auto_rollback_true():
    # Handler returns is_error; checkpoint.restore invoked; result.metadata.rolled_back=True.

def test_no_rollback_when_auto_rollback_false():
    # Handler returns is_error but tool has auto_rollback=False; restore NOT called.

def test_disabled_when_trust_config_checkpointing_false():
    # config.trust.checkpointing=False → checkpoint.create never called.
```

### F4 Rate limit

```python
def test_under_cap_allows_all_calls():
    # N calls where N < max_per_minute → all invoked.

def test_over_cap_rejects_immediately():
    # N+1th call → is_error, metadata.rate_limited=True, metadata.retry_after_s set.

def test_window_slides_after_60s():
    # Push through cap; advance time by 61s; next call succeeds.

def test_rate_limit_disabled_via_config():
    # config.tools.rate_limits=False → unlimited.
```

## 7. Known risks

| Risk | Mitigation |
|---|---|
| Circuit breaker trips too aggressively on legitimate transient issues | Conservative defaults (5/60s) + per-tool override. Telemetry via `meta.health` surfaces trips. |
| Idempotency key collisions across sessions | Session-scoped store; cross-session reuse is physically impossible. |
| Auto-checkpoint silently captures more than intended | Only paths in args are snapshotted; tools without path args skip (and agent knows the limitation from tool descriptions). |
| Rate limits create mystery failures for users | Error message includes exact `retry_after_s`; agent can reason over it. User can disable via global flag. |
| Performance regression on hot path | Benchmark required (see §8 Done when). 3 new dict lookups + 1 deque append should be <0.1ms. |

## 8. Done when

- [ ] All 4 features implemented behind their feature flags
- [ ] 18+ new pytest tests green
- [ ] Benchmark showing happy-path overhead <5% vs. pre-F dispatcher
- [ ] Circuit state + rate-limit remaining surface in `meta.health` output
      (for PROPOSAL D integration)
- [ ] System prompt text for exclusive tools notes the `idempotency_key` arg
- [ ] No regression in existing Phase B/C tests

## 9. Out of scope

- Cross-session idempotency stores (SQLite, redis, etc.) → PROPOSAL-G
- Global kill-switch for all tools (contrary to §2)
- User-facing CLI for inspecting circuit/rate state (`:PoorCLIDiag`
  absorbs this via `meta.health` in Phase D)
- Rewriting the trust/permission system
- Auto-recovering from checkpoint on session crash (separate concern:
  that's session resume, not tool-call robustness)
