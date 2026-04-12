# PRD 004: Fix semantic cache key to hash file contents, not file list

- **Wave:** 1
- **Status:** ready
- **Owner (human):** @gongahkia
- **Estimated effort:** small (1d)
- **Blocks:** 027
- **Blocked by:** —
- **Files it mutates:**
  - `poor_cli/semantic_cache.py`
  - `poor_cli/file_cache.py` (read-only usage; may need a small API addition)
  - call sites of the semantic cache (grep `semantic_cache`)
- **New files it adds:**
  - `tests/test_semantic_cache_key.py`

---

## 1. Problem

`poor_cli/semantic_cache.py` caches assistant *responses* keyed by `(prompt_hash, context_hash)`. The current `context_hash` is computed from the **file list** (paths + maybe mtimes), not the **file contents**.

Consequence: the user edits a file, re-asks the same question, and gets a *stale cached answer* describing the pre-edit file. No warning, no invalidation signal. Silent correctness bug.

[`LEARNING.md` §2.1](../LEARNING.md): "Change a file → cache hits return stale answers → user sees bizarre 'out of date' replies with no warning. Hash contents, or bust cache on any mtime change."

## 2. Current state

The implementation approximately:

```python
# semantic_cache.py (conceptually)
def _context_hash(self, context: ContextBundle) -> str:
    key = hashlib.sha256()
    for file in sorted(context.files, key=lambda f: f.path):
        key.update(file.path.encode())
        # maybe: key.update(str(file.mtime).encode())
    return key.hexdigest()
```

Cache key = `sha256(prompt) + sha256(file-list)`. An edit to `file.path` does not perturb the cache key.

## 3. Goal & non-goals

**Goal:** the cache key incorporates a stable content fingerprint for every file in context. Edits invalidate the cache. False-positive hits disappear.

**Non-goals:**
- Do not re-architect `semantic_cache.py`.
- Do not introduce a new caching layer (see PRD 027 for block-level caching).
- Do not hash enormous files byte-by-byte on every lookup — use `file_cache.py`'s existing mtime+size quick check plus content hash only when mtime changes.

## 4. Design

### 4.1 Fingerprinting

`file_cache.py` already reads files and caches them. Add a `content_fingerprint(path: Path) -> str` helper there:

```python
def content_fingerprint(path: Path) -> str:
    """
    Returns a stable hash of file contents.
    Uses stat().st_mtime_ns + st_size as quick invalidation; computes sha256
    lazily and caches by (path, mtime_ns, size).
    """
```

This ensures we don't re-hash unchanged files.

### 4.2 Cache key

```python
def _context_hash(self, context: ContextBundle) -> str:
    key = hashlib.sha256()
    for f in sorted(context.files, key=lambda x: x.path):
        key.update(f.path.encode())
        key.update(b"\x00")
        key.update(file_cache.content_fingerprint(Path(f.path)).encode())
        key.update(b"\x01")
    # system prompt & instructions fold in too — see 4.3
    key.update(context.system_prompt_hash.encode())
    return key.hexdigest()
```

### 4.3 Include system prompt + tool schemas in the key

While we're here, also fold in:
- system prompt hash (already available),
- active tool schema hash (PAIN-POINTS.md #6),
- active rules/memory hash (AGENTS.md / CLAUDE.md contents).

Any change to these *should* invalidate response cache.

### 4.4 Stale-cache observability

Add a counter the audit log writes on every cache hit / miss / invalidation. Exposed via the eventual cost dashboard (PRD 016).

## 5. Files to create / modify / delete

**Create**
- `tests/test_semantic_cache_key.py`

**Modify**
- `poor_cli/semantic_cache.py` — new `_context_hash` that uses content fingerprints + system-prompt / tool-schema / rules hashes.
- `poor_cli/file_cache.py` — add `content_fingerprint(path)` helper with mtime+size memoization.
- call sites of `semantic_cache` — no signature change; safe refactor.

**Delete** — none.

## 6. Implementation plan

1. Add `content_fingerprint` to `file_cache.py` with a small LRU cache keyed on `(path, mtime_ns, size)`. Unit test it.
2. Update `semantic_cache.py::_context_hash` to call the fingerprint. Include system prompt / tool-schema / rules hashes.
3. Bump the on-disk cache version if the cache is persisted (if `semantic_cache.db` exists, add a `meta.schema_version = 2` row and clear the old cache on first load). Coordinate with PRD 003 framework.
4. Write regression test: build a `ContextBundle` with one file at path X; compute key; edit the file on disk; compute key again; assert keys differ.
5. Write false-positive test from the original bug: same path, same mtime, different content (rare but possible if content is rewritten in-place within the same second) — assert the content hash still invalidates.
6. Run `make lint && make test`.

## 7. Testing & acceptance criteria

**New tests in `tests/test_semantic_cache_key.py`**
- `test_key_changes_when_file_content_changes`
- `test_key_stable_when_nothing_changes`
- `test_key_changes_when_system_prompt_changes`
- `test_key_changes_when_tool_schema_changes`
- `test_fingerprint_cached_by_mtime`
- `test_stale_cache_regression_from_readme_example`

**Commands to pass**
- `make lint && make test`

**Done criterion**
- [ ] `_context_hash` incorporates content fingerprints.
- [ ] Edit → cache miss (proven by test).
- [ ] No new disk-I/O per lookup on unchanged files (proven by fingerprint memoization test).
- [ ] Audit log records cache hit / miss events.

## 8. Rollback / risk

Users will experience a **one-time cache miss rate spike** after upgrading (old keys no longer match). This is intentional. Document in release notes.

## 9. Out-of-scope & boundary

- 🚫 Do not implement block-level / non-prefix caching (PRD 027).
- 🚫 Do not change the response shape returned from the cache.
- 🚫 Do not replace `semantic_cache.py`'s similarity logic or embedding backend.

## 10. Related PRDs & references

- LEARNING.md §2.1 "Semantic cache key is weak."
- PRD 027 (block-level caching) builds on this.
- PAIN-POINTS.md #13 (duplicate query re-inference).
