# PRD 021: CI gate — pin `core.py` under 1,000 lines

- **Wave:** 2
- **Status:** ready
- **Owner (human):** @gongahkia
- **Estimated effort:** small (1d)
- **Blocks:** —
- **Blocked by:** 017, 018
- **Files it mutates:**
  - `.github/workflows/tests.yml` (add one job)
  - or `Makefile` (add a `make lint-sizes` target)
- **New files it adds:**
  - `scripts/check_monolith_sizes.py`

## 1. Problem

Once `core.py` is decomposed (PRDs 017, 018), nothing prevents it from re-growing. Without a gate, every feature request adds 100 lines until the monolith returns. LEARNING.md §2.1 explicitly recommends this gate.

## 2. Current state

No line-count enforcement anywhere.

## 3. Goal & non-goals

**Goal:** CI fails if `core.py` > 1,000 lines, `server/runtime.py` > 800 lines, `config.py` > 1,500 lines, or any single Python file > 2,000 lines. Clear error message with the delta.

**Non-goals:**
- Do not enforce line counts on Lua files (too variable in the ecosystem).
- Do not enforce on test files.
- Do not set aesthetic limits (80-char lines, etc.) — ruff handles that.

## 4. Design

```python
# scripts/check_monolith_sizes.py
#!/usr/bin/env python3
import sys
from pathlib import Path

HARD_LIMITS = {
    "poor_cli/core.py":           1_000,
    "poor_cli/server/runtime.py":   800,
    "poor_cli/config.py":         1_500,
}
GLOBAL_FILE_LIMIT = 2_000  # applies to every .py under poor_cli/

def main() -> int:
    errors: list[str] = []
    repo_root = Path(__file__).parent.parent
    for path, limit in HARD_LIMITS.items():
        p = repo_root / path
        if not p.exists():
            continue
        lines = p.read_text().count("\n")
        if lines > limit:
            errors.append(f"{path}: {lines} lines > {limit} limit (overage {lines - limit})")
    for p in (repo_root / "poor_cli").rglob("*.py"):
        lines = p.read_text().count("\n")
        if lines > GLOBAL_FILE_LIMIT and str(p.relative_to(repo_root)) not in HARD_LIMITS:
            errors.append(f"{p.relative_to(repo_root)}: {lines} > {GLOBAL_FILE_LIMIT}")
    for e in errors:
        print(f"::error::{e}", file=sys.stderr)
    return 1 if errors else 0

if __name__ == "__main__":
    sys.exit(main())
```

Wire into CI as a fast pre-test step. Also add `make lint-sizes`.

## 5. Files to create / modify / delete

**Create**
- `scripts/check_monolith_sizes.py`

**Modify**
- `.github/workflows/tests.yml` — add a step before Python tests.
- `Makefile` — `lint-sizes: ## check monolith sizes` target.

## 6. Implementation plan

1. Land the script. Run locally — confirm passes after PRD 017/018 land (and fails if you pretend-bloat `core.py`).
2. Wire into CI.
3. `make lint && make test && make lint-sizes`.

## 7. Testing & acceptance criteria

- `test_script_fails_on_oversized_file_fixture` (copy a fake too-big file into a temp dir via pytest fixture).
- CI job is visible in PR checks.

**Done criterion**
- [ ] Script exists and runs locally.
- [ ] CI enforces it.
- [ ] Contributors blocked from merging a file over limit without explicit override.

## 8. Rollback / risk

Very low. Override in the script itself (add an explicit exception — comment required).

## 9. Out-of-scope & boundary

- 🚫 Do not set line limits below what PRD 017/018 actually deliver — budget slack (e.g., allow 1,000 when core hits 900 after decomposition).
- 🚫 Do not enforce on tests/, docs/, asset/.

## 10. Related PRDs & references

- PRD 017, 018 make this enforceable.
- LEARNING.md §2.2.
