# PRD 002: Async-only permission callback (remove sync/async duck-typing)

- **Wave:** 1
- **Status:** ready
- **Owner (human):** @gongahkia
- **Assignee (agent):** _unassigned_
- **Estimated effort:** small (1d)
- **Blocks:** 017
- **Blocked by:** —
- **Files it mutates:**
  - `poor_cli/core.py` (callback call site only)
  - `poor_cli/permission_engine.py`
  - `poor_cli/server/runtime.py` (server-side callback registration)
  - Any CLI / Neovim bridge that registers a permission callback
- **New files it adds:**
  - `tests/test_permission_callback_async.py`

---

## 1. Problem

`poor_cli/core.py` catches `TypeError` around its permission-callback invocation to distinguish between a sync and an async callable. This pattern:

```python
# roughly, in core.py near line 97
try:
    result = self._permission_callback(tool_name, args)
    if inspect.isawaitable(result):
        result = await result
except TypeError:
    result = await self._permission_callback(tool_name, args)
```

This is not type safety — it is a silent-failure factory. If a sync callback raises `TypeError` for unrelated reasons (wrong argument, bad subscript, bad attribute access), the exception gets swallowed and retry-as-async runs, which may then produce a different error or silently succeed with wrong state.

[`LEARNING.md` §2.1](../LEARNING.md) calls this out as a P0 fix: "Make it async-only. Effort: 1 day."

## 2. Current state

The permission callback is invoked when a tool with mutating semantics (e.g., `write_file`, `bash`, `git_commit`) asks `PermissionEngineMixin.request()` to gate it. Callbacks arrive from:

- The Neovim client via `server/runtime.py` (registered as async by default).
- The CLI prompt-based flow in `poor_cli/cli/*` (currently registered as sync in some call sites).
- Automation / test fixtures.

Consumers of the callback include `permission_engine.py` and `policy_hooks.py`. Any of them today can accept either shape. This ambiguity has propagated.

Find every callback registration with:

```
grep -rn "permission_callback\|set_permission_callback\|register_permission\|_permission_callback" poor_cli/ nvim-poor-cli/ tests/
```

## 3. Goal & non-goals

**Goal:** the permission callback type is `Callable[[str, dict], Awaitable[dict]]`. No `TypeError`-catching. All existing callbacks either already are async or get wrapped at registration time by a tiny helper. Type-checkers (ruff + optional `mypy --strict` in the future) can verify.

**Non-goals:**
- Do not change the shape of the permission decision dict.
- Do not change when or which tools trigger permission.
- Do not refactor `permission_engine.py` beyond what the signature change demands.

## 4. Design

1. Define the type alias in `permission_engine.py`:

```python
from collections.abc import Awaitable, Callable

PermissionDecision = dict  # keep as-is to avoid broader refactor
PermissionCallback = Callable[[str, dict], Awaitable[PermissionDecision]]
```

2. Add a helper at the module boundary that *wraps* a sync callback into an async one, for legacy call sites:

```python
def _as_async(cb) -> PermissionCallback:
    import inspect, functools
    if inspect.iscoroutinefunction(cb):
        return cb
    @functools.wraps(cb)
    async def wrapped(tool: str, args: dict) -> PermissionDecision:
        return cb(tool, args)
    return wrapped
```

The helper lives once in `permission_engine.py`. The registration APIs use it so callers can continue to pass sync for tests and fixtures.

3. Delete the `try/except TypeError` block in `core.py`. Replace with a single `await self._permission_callback(...)`. Assert at registration time that the stored callback is a coroutine function (via `inspect.iscoroutinefunction`).

4. Document in the callback's docstring: "This callable MUST be a coroutine function. Use `_as_async` if you're wrapping a legacy sync function."

## 5. Files to create / modify / delete

**Create**
- `tests/test_permission_callback_async.py` — tests below.

**Modify**
- `poor_cli/permission_engine.py` — add `PermissionCallback` type alias + `_as_async` helper; update `set_permission_callback`-like registrations to wrap if needed.
- `poor_cli/core.py` — remove the `try/except TypeError` path; `await self._permission_callback(tool_name, args)` unconditionally. **Do not touch anything else in core.py.**
- `poor_cli/server/runtime.py` — ensure the server-side registration of its RPC-backed callback is async-native (it should be; verify and remove any defensive code).
- `poor_cli/cli/*.py` — any CLI registration of a sync callback wraps via `_as_async`.
- `poor_cli/policy_hooks.py` — if it registers or calls the permission callback, same treatment.

**Delete** — none.

## 6. Implementation plan

1. Read `poor_cli/core.py` around the permission call site (grep for `_permission_callback`) to find the exact try/except block.
2. Add the type alias and `_as_async` helper in `permission_engine.py`.
3. Identify every registration site (use the grep above) and add wrapping where a sync fn is passed.
4. Remove the try/except block in `core.py`; replace with an `assert inspect.iscoroutinefunction(self._permission_callback)` guard at registration time.
5. Write tests:
   - Registering an async callback works and is awaited.
   - Registering a sync callback via `_as_async` works and is awaited.
   - Registering a raw sync callback without `_as_async` raises a clear error at registration (not at first call).
   - A callback that raises `TypeError` for an unrelated reason propagates the exception rather than being silently retried.
6. Run `make lint && make test`.

## 7. Testing & acceptance criteria

**New tests in `tests/test_permission_callback_async.py`**

- `test_async_callback_awaited`
- `test_sync_callback_wrapped_via_as_async`
- `test_raw_sync_callback_rejected_at_registration`
- `test_unrelated_typeerror_propagates` — **this is the regression test for the original bug.**
- `test_permission_decision_shape_unchanged`

**Commands to pass**
- `make lint && make test`

**Manual verification**
- Run a prompt that triggers a mutating tool (`poor-cli exec --prompt "write a hello.txt"`); confirm the permission prompt still works end-to-end in CLI and the Neovim bridge.

**Done criterion**
- [ ] No `except TypeError` near the permission callback anywhere in `poor_cli/`.
- [ ] `grep -n "_permission_callback" poor_cli/core.py` shows exactly one `await` call and no ceremony.
- [ ] Registration enforces coroutine-ness.
- [ ] All tests pass.

## 8. Rollback / risk

Very low. Behavior-preserving for async callers. The one user-visible change: a sync callback that was previously "tolerated" now raises at registration time. We accept that; PRD explicitly wraps legacy sync fixtures at their registration site.

## 9. Out-of-scope & boundary

- 🚫 Do not refactor `permission_engine.py` beyond what the signature change demands.
- 🚫 Do not change the permission decision dict shape, keys, or values.
- 🚫 Do not touch the audit log schema.
- 🚫 Do not touch `core.py` beyond the single callback call site.

## 10. Related PRDs & references

- LEARNING.md §2.1 "Permission callback is sync-vs-async by try/except."
- PRD 017 (core pre-slice) depends on this — the cleaner call site simplifies the extraction.
