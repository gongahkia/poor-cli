# PRD 005: Consolidate `watch.py` and `ide_watch.py` into a single watcher

- **Wave:** 1
- **Status:** ready
- **Owner (human):** @gongahkia
- **Estimated effort:** small (1–2d)
- **Blocks:** 042
- **Blocked by:** —
- **Files it mutates:**
  - `poor_cli/watch.py`
  - `poor_cli/ide_watch.py`
  - call sites that import either (use `grep -rn "from poor_cli.watch\|from poor_cli.ide_watch\|import watch\b\|import ide_watch\b" poor_cli/ nvim-poor-cli/ tests/`)
- **New files it adds:**
  - `tests/test_file_watcher.py`

---

## 1. Problem

The repository has two independent file-watcher implementations:

- `poor_cli/watch.py` — older, async-generator pattern, ~31 lines.
- `poor_cli/ide_watch.py` — newer, callback pattern, 150+ lines.

They don't share code. Bugs fixed in one don't fix the other. Contributors have to reverse-engineer which is canonical. [`LONGTERM-TODO.md` L2](../LONGTERM-TODO.md) flags this; [`LEARNING.md` §1.6](../LEARNING.md) recommends deletion of the duplicate.

## 2. Current state

Call sites (grep-able):
- `watch.py` is imported from the `/watch` command flow.
- `ide_watch.py` is imported by newer plan-mode / QA-watch paths.

They diverge on: shutdown semantics, debounce window, `.gitignore` handling, file-add vs file-change events.

## 3. Goal & non-goals

**Goal:** one module, one class, one API. Feature-parity with the richer of the two. All call sites migrated. The other module is deleted. Tests prove both the legacy async-generator consumer and the callback consumer patterns keep working via a single implementation.

**Non-goals:**
- No new features (respect ignore patterns, recursion, symlinks — keep current behavior, pick the better of the two).
- No cross-platform fanciness (the existing two already work; unify, don't expand).

## 4. Design

Pick `ide_watch.py` as the survivor (richer, newer, more tests likely). Rename to `poor_cli/file_watcher.py` to eliminate ambiguity. Add an `as_async_generator()` method for callers that want the old `watch.py` consumption pattern:

```python
# poor_cli/file_watcher.py
class FileWatcher:
    def __init__(self, root: Path, *, debounce_ms: int = 150, ignore: list[str] | None = None): ...
    def on_change(self, callback: Callable[[FileEvent], None]) -> None: ...
    def start(self) -> None: ...
    def stop(self) -> None: ...
    async def __aiter__(self) -> AsyncIterator[FileEvent]:  # legacy pattern
        ...
```

Call sites that imported `watch.py` switch to `from poor_cli.file_watcher import FileWatcher` and use `async for evt in watcher:`. Call sites that imported `ide_watch.py` switch to `from poor_cli.file_watcher import FileWatcher` and use `watcher.on_change(cb)`.

Both patterns backed by one event queue.

## 5. Files to create / modify / delete

**Create**
- `poor_cli/file_watcher.py` — consolidated implementation.
- `tests/test_file_watcher.py`

**Modify**
- Every importer (see grep in problem section).

**Delete**
- `poor_cli/watch.py`
- `poor_cli/ide_watch.py`

## 6. Implementation plan

1. Copy `ide_watch.py` content to `poor_cli/file_watcher.py`. Rename class to `FileWatcher`.
2. Port the `__aiter__` method from `watch.py` into the new class.
3. Update every import (grep above). Keep signatures the same where possible.
4. Delete `watch.py` and `ide_watch.py`.
5. Write tests for both consumption patterns.
6. Run `make lint && make test`.

## 7. Testing & acceptance criteria

**New tests**
- `test_callback_pattern_receives_events`
- `test_async_generator_pattern_receives_events`
- `test_gitignore_respected`
- `test_stop_is_idempotent`
- `test_debounce_coalesces_rapid_changes`

**Commands**
- `make lint && make test`

**Manual**
- `poor-cli watch` (if exposed as CLI) still works.
- `/watch` slash command still works from the Neovim client.

**Done criterion**
- [ ] `poor_cli/watch.py` and `poor_cli/ide_watch.py` are gone.
- [ ] `poor_cli/file_watcher.py` exists with tests.
- [ ] No `ImportError` on `make test`.

## 8. Rollback / risk

Low. If a caller still uses the old generator pattern and we missed it, we get an `ImportError` at runtime. Mitigate by grep-sweep before commit.

## 9. Out-of-scope & boundary

- 🚫 Do not add new event types (create, rename, etc.) — ship parity only.
- 🚫 Do not change `.poor-cli/` layout.

## 10. Related PRDs & references

- LONGTERM-TODO L2.
- LEARNING.md §1.6.
