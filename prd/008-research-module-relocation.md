# PRD 008: Move research modules to `poor_cli/research/` with feature flags

- **Wave:** 1
- **Status:** ready
- **Owner (human):** @gongahkia
- **Estimated effort:** small (1–2d)
- **Blocks:** 059
- **Blocked by:** 007
- **Files it mutates:**
  - `poor_cli/latent_communication.py` → moves
  - `poor_cli/neural_code_encoder.py` → moves
  - `poor_cli/code_tokenizer.py` → moves (if not shipping — see PRD 058)
  - `poor_cli/speculative_decoding.py` → moves (per PRD 007 decision)
  - `poor_cli/kv_cache_store.py` → moves (per PRD 007 decision)
  - `poor_cli/embeddings.py` → stays if actively used; moves if not
  - `poor_cli/__init__.py` — exports
  - `pyproject.toml` — package list
- **New files it adds:**
  - `poor_cli/research/__init__.py`
  - `poor_cli/research/README.md`

## 1. Problem

Research modules live in the primary package. They cost cold-start time (imports), cognitive overhead (contributors reading code that never runs), and repo noise. [`LEARNING.md` §1.5 & §1.6](../LEARNING.md): "Move all research modules into `poor_cli/research/` and lazy-import them."

## 2. Current state

Primary-package research modules (verify before moving — list is from LEARNING.md §1.5):

- `latent_communication.py`
- `neural_code_encoder.py`
- `speculative_decoding.py` (PRD 007 decides fate)
- `kv_cache_store.py` (PRD 007)
- `code_tokenizer.py` (PRD 058 may ship; if so, do not move)
- `embeddings.py` (check: is `semantic_cache` using it?)

## 3. Goal & non-goals

**Goal:** each research module lives in `poor_cli/research/` and loads only when a feature flag or config entry enables it. Cold start time drops. Contributors reading `poor_cli/` see only production code.

**Non-goals:**
- Do not delete any of them (PRD 007 does that per decision).
- Do not re-implement — just relocate + flag.
- Do not change module APIs; update imports.

## 4. Design

### 4.1 Layout

```
poor_cli/
  research/
    __init__.py            # empty; feature-flag aware
    README.md              # "Research code. Not part of production agent loop."
    latent_communication.py
    neural_code_encoder.py
    speculative_decoding.py   # if not deleted
    kv_cache_store.py         # if not shipped
```

### 4.2 Lazy-import pattern

`poor_cli/research/__init__.py`:

```python
"""
Research modules. Not imported at poor-cli startup.
Enable individually via config:
    [research]
    latent_communication = false
    neural_code_encoder  = false
"""
# explicit: no * imports; callers must `from poor_cli.research import latent_communication`
```

Any production code that *optionally* wants a research feature guards the import:

```python
def _maybe_get_latent():
    if not config.get("research.latent_communication", False):
        return None
    from poor_cli.research import latent_communication
    return latent_communication
```

### 4.3 Config entries

Add a `[research]` section to `preferences.json` schema (coordinated with PRD 003):

```json
{
  "research": {
    "latent_communication": false,
    "neural_code_encoder": false,
    "speculative_decoding": false,
    "kv_cache_store": false
  }
}
```

## 5. Files to create / modify / delete

**Create**
- `poor_cli/research/__init__.py`
- `poor_cli/research/README.md`

**Modify**
- Move each research module (git-level move to preserve blame).
- `poor_cli/__init__.py` — drop any top-level re-exports of research modules.
- Production-code call sites — switch to lazy-import guard.
- `pyproject.toml::[tool.setuptools].packages` — add `"poor_cli.research"`.

**Delete** — none (PRD 007 owns deletions).

## 6. Implementation plan

1. Confirm PRD 007 decisions. Do not move anything PRD 007 decided to delete.
2. `git mv poor_cli/latent_communication.py poor_cli/research/latent_communication.py` etc.
3. Update imports across the codebase. Grep: `grep -rn "from poor_cli.latent_communication\|from poor_cli.neural_code_encoder\|from poor_cli.speculative_decoding\|from poor_cli.kv_cache_store"`.
4. Replace eager imports with the lazy-guard pattern in production code.
5. Add the `[research]` config defaults.
6. Update `pyproject.toml` packages list.
7. Add `poor_cli/research/README.md` describing the relocation and rules for adding new research modules (must land behind a flag, default off).
8. Run `make lint && make test`.

## 7. Testing & acceptance criteria

**New tests**
- `tests/test_research_relocation.py::test_research_modules_not_imported_by_default` — `import poor_cli` must not pull any `poor_cli.research.*` module (verify via `sys.modules`).
- `tests/test_research_relocation.py::test_feature_flag_enables_research_module`

**Commands**
- `make lint && make test`
- Cold-start measurement: `python3 -c "import time; s=time.time(); import poor_cli; print(time.time()-s)"` — document the before/after in the PR description.

**Done criterion**
- [ ] All research modules live under `poor_cli/research/`.
- [ ] `import poor_cli` does not import any research module.
- [ ] Tests prove flag gating.

## 8. Rollback / risk

Low. Git mv preserves history. If a caller was silently relying on a top-level export, restore the re-export with a deprecation warning.

## 9. Out-of-scope & boundary

- 🚫 Do not modify research module internals.
- 🚫 Do not delete anything — PRD 007 owns deletions.
- 🚫 Do not ship a research feature in this PRD (e.g., do not enable `latent_communication` by default).

## 10. Related PRDs

- PRD 007 (stub decisions).
- PRD 059 (latent communication ship-or-archive decision).
- LEARNING.md §1.5, §1.6.
