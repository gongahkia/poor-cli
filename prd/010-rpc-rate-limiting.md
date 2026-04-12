# PRD 010: Rate-limit the RPC surface

- **Wave:** 1
- **Status:** ready
- **Owner (human):** @gongahkia
- **Estimated effort:** small-to-medium (2d)
- **Blocks:** 019
- **Blocked by:** —
- **Files it mutates:**
  - `poor_cli/server/runtime.py` (narrow — one middleware registration only)
  - `poor_cli/server/transport.py`
- **New files it adds:**
  - `poor_cli/server/rate_limit.py`
  - `tests/test_server_rate_limit.py`

## 1. Problem

The JSON-RPC server exposes ~100 methods to the Neovim client over stdio. A rogue client, a bug, or a loop can pound the server (e.g., firing `chatStreaming` in a tight loop). The current surface has no rate limit, no request coalescing, and no backpressure. LEARNING.md §2.3: "No rate limiting on RPC. A rogue Lua client (or a bug) can pound the server."

In production this is also a cost-safety issue: a buggy keymap firing 100 completions a second translates directly to provider spend.

## 2. Current state

Requests land in `server/runtime.py`, dispatch by method name, and execute. There is no pre-dispatch limiter. Reference:

```
grep -n "dispatch\|handle_request\|run_method" poor_cli/server/runtime.py
```

## 3. Goal & non-goals

**Goal:** every inbound RPC call passes through a configurable rate limiter. Hot methods (`chatStreaming`, completions) have a lower rate than cold methods (`getStatus`). Exceeding the limit returns a structured JSON-RPC error `429`-equivalent rather than blocking the server.

**Non-goals:**
- Do not add per-user rate limiting (single local user — global limits are enough).
- Do not queue dropped requests (they return an error; client decides whether to retry).
- Do not add token-count-aware limits (separate concern; economy does this already for LLM calls).

## 4. Design

### 4.1 Algorithm

Token-bucket per method group, configured in `preferences.json`:

```json
{
  "rpc_rate_limits": {
    "default": {"rate": 50, "burst": 100},
    "chatStreaming": {"rate": 2, "burst": 4},
    "completions/*": {"rate": 10, "burst": 20}
  }
}
```

`rate` = steady-state requests/sec; `burst` = bucket size.

### 4.2 Module shape

```python
# poor_cli/server/rate_limit.py
from __future__ import annotations
from dataclasses import dataclass
from time import monotonic

@dataclass
class Bucket:
    capacity: float
    tokens: float
    last_refill: float
    refill_rate: float  # tokens/sec

class RateLimiter:
    def __init__(self, config: dict[str, dict[str, float]]): ...

    def take(self, method: str, now: float | None = None) -> bool:
        """Return True if request can proceed; False if rate-limited."""

    def set_config(self, config: dict) -> None: ...

class RateLimitExceeded(Exception):
    def __init__(self, method: str, retry_after_s: float): ...
```

### 4.3 Integration

One line in the dispatch path: if `not limiter.take(method)`, return `JsonRpcError(code=-32029, message="rate limited", data={"method": method, "retry_after_s": ...})`. Code `-32029` is in the JSON-RPC server-reserved range.

### 4.4 Observability

Emit `rpc.rate_limit.exceeded` events to the audit log with method name + client id.

## 5. Files to create / modify / delete

**Create**
- `poor_cli/server/rate_limit.py`
- `tests/test_server_rate_limit.py`

**Modify**
- `poor_cli/server/runtime.py` — register the limiter, call `take()` at dispatch. **Do not refactor runtime.py broadly.** PRD 019 owns partitioning.

## 6. Implementation plan

1. Implement `Bucket` + `RateLimiter` with pattern-matched method lookup (`chatStreaming` > `*` glob fallback to `default`).
2. Wire one call site in `runtime.py` dispatch.
3. Write tests: steady-state, burst, glob pattern, config reload.
4. Add audit-log event.
5. `make lint && make test`.

## 7. Testing & acceptance criteria

**New tests**
- `test_bucket_refills_over_time`
- `test_take_returns_false_when_exhausted`
- `test_hot_method_limited_lower_than_default`
- `test_glob_pattern_matches_method_group`
- `test_rate_limit_emits_audit_event`
- `test_rpc_returns_structured_error_when_limited` — integration.

**Commands**
- `make lint && make test`

**Done criterion**
- [ ] Limiter wired at dispatch.
- [ ] Config supports per-method + glob + default.
- [ ] Limit-exceeded returns JSON-RPC error, does not kill server.

## 8. Rollback / risk

Low. Can disable with `rpc_rate_limits: {}` config.

## 9. Out-of-scope & boundary

- 🚫 Do not partition `runtime.py`. PRD 019 owns that.
- 🚫 Do not add cross-user quota tracking.

## 10. Related PRDs

- PRD 019 (runtime partition) is blocked by this so the limiter lands before the partition.
- LEARNING.md §2.3.
