# PRD 019: Partition `server/runtime.py` into `handlers/` packages

- **Wave:** 2
- **Status:** ready
- **Owner (human):** @gongahkia
- **Estimated effort:** large (3w)
- **Blocks:** 025 and anything adding new RPC methods
- **Blocked by:** 010
- **Files it mutates:**
  - `poor_cli/server/runtime.py`
- **New files it adds:**
  - `poor_cli/server/handlers/__init__.py`
  - `poor_cli/server/handlers/chat.py`
  - `poor_cli/server/handlers/tools.py`
  - `poor_cli/server/handlers/config.py`
  - `poor_cli/server/handlers/sessions.py`
  - `poor_cli/server/handlers/checkpoints.py`
  - `poor_cli/server/handlers/providers.py`
  - `poor_cli/server/handlers/tasks.py`
  - `poor_cli/server/handlers/automations.py`
  - `poor_cli/server/handlers/memory.py`
  - `poor_cli/server/handlers/multiplayer.py`
  - `poor_cli/server/handlers/status.py`
  - `poor_cli/server/handlers/context.py`
  - `poor_cli/server/handlers/trust.py`
  - `poor_cli/server/registry.py`
  - `tests/test_server_handlers.py`

## 1. Problem

`server/runtime.py` is ~6,300 lines, hosts ~100 RPC methods, and mixes multiplayer state-machine code with plain handlers. Contributors can't modify one method without reading the whole file. LEARNING.md §2.1 calls this out as a structural problem equal to `core.py`.

## 2. Current state

All handlers in one class (or one file). Method dispatch via a single table.

## 3. Goal & non-goals

**Goal:** every handler lives in the right `handlers/*.py`. Each module self-registers via a decorator. `runtime.py` holds only dispatch + transport. Multiplayer state machine moves to its own module. Size targets: every handler file ≤500 lines; `runtime.py` ≤800 lines.

**Non-goals:**
- Do not change any method signature or behavior.
- Do not introduce OpenAPI / JSON Schema docs (nice-to-have follow-up).

## 4. Design

### 4.1 Registry

```python
# poor_cli/server/registry.py
from collections.abc import Awaitable, Callable
from typing import Any

Handler = Callable[["RpcContext", dict], Awaitable[Any]]
REGISTRY: dict[str, Handler] = {}

def rpc(method: str):
    def deco(fn: Handler) -> Handler:
        REGISTRY[method] = fn
        return fn
    return deco
```

### 4.2 Per-file shape

```python
# poor_cli/server/handlers/chat.py
from poor_cli.server.registry import rpc

@rpc("poor-cli/chat")
async def chat(ctx, params): ...

@rpc("chat")                 # legacy alias
async def chat_legacy(ctx, params): ...

@rpc("poor-cli/chatStreaming")
async def chat_streaming(ctx, params): ...
```

`handlers/__init__.py` imports each module to trigger registration.

### 4.3 Dispatch

`runtime.py::dispatch(method, params, ctx)` looks up `REGISTRY.get(method)` and calls it. Rate limiter (PRD 010) runs before lookup.

### 4.4 Multiplayer

Move all `multiplayer_*` methods and their shared state into `handlers/multiplayer.py` + `poor_cli/server/multiplayer_state.py`. Delete the multiplayer state-machine code from `runtime.py`.

## 5. Files to create / modify / delete

See header.

## 6. Implementation plan

1. Land `registry.py` + `handlers/__init__.py` with empty modules. Wire `runtime.py` dispatch through the registry but keep current handlers in place (they won't register yet — no collision).
2. For each handler category (chat, tools, config, …), move methods one group at a time:
   - Copy methods to `handlers/<group>.py`.
   - Decorate with `@rpc(...)`.
   - Remove from `runtime.py`.
   - Run `make test` after each group.
3. Move multiplayer last — highest risk, so biggest safety net.
4. Validate `runtime.py` size ≤800 lines at the end.
5. Write registry tests.
6. `make lint && make test`.

## 7. Testing & acceptance criteria

- `test_registry_registers_unique_methods`
- `test_every_known_method_still_reachable` — list the ~100 methods; ensure dispatch works for each (smoke).
- `test_runtime_py_under_800_lines`

**Done criterion**
- [ ] Every handler in the correct package.
- [ ] `runtime.py` ≤800 lines.
- [ ] Multiplayer state machine in its own module.
- [ ] All tests pass unchanged.

## 8. Rollback / risk

Medium. Mechanical; per-group rollback via git.

## 9. Out-of-scope & boundary

- 🚫 Do not change behavior.
- 🚫 Do not introduce API versioning.
- 🚫 Do not rename methods.

## 10. Related PRDs & references

- PRD 010 (rate limit) lands first to avoid conflict at dispatch layer.
- PRD 025 (streaming tool output) lands after.
- LEARNING.md §2.1.
