# PRD 026: RTK-lite — Python-side shell output filter (start with `git status`)

- **Wave:** 2
- **Status:** ready
- **Owner (human):** @gongahkia
- **Estimated effort:** medium (1w + incremental)
- **Blocks:** —
- **Blocked by:** —
- **Files it mutates:**
  - `poor_cli/tools_async.py`
  - `poor_cli/tool_output_filter.py`
- **New files it adds:**
  - `poor_cli/rtk_lite/__init__.py`
  - `poor_cli/rtk_lite/git_filter.py`
  - `poor_cli/rtk_lite/npm_filter.py` (stretch)
  - `poor_cli/rtk_lite/cargo_filter.py` (stretch)
  - `tests/test_rtk_lite_git.py`

## 1. Problem

"RTK (Rust Token Killer)" was documented in SOLUTIONS.md with 60–90% token-savings claims on common shell commands. `rtk_integration.py` is a 2-line stub. LEARNING.md §2.2: "Ship one piece of RTK. Pick the highest-ROI shell command and implement output filtering in Python (no Rust binary needed yet)."

PAIN-POINTS.md #9 (ambient noise pollution) is the target pain.

## 2. Current state

`tool_output_filter.py` can transform JSON/YAML by JSONPath, but it's opt-in per tool call. No filters registered for common shell commands. `bash` tool returns raw output.

## 3. Goal & non-goals

**Goal:** `bash` tool recognizes a handful of high-signal commands and post-processes their output with purpose-built filters, reducing tokens while preserving decision-relevant information. Ship `git status`, `git diff --stat`, `ls -la`. Stretch: `npm install`, `cargo build`. Python-only; no Rust.

**Non-goals:**
- Do not ship a Rust binary in this PRD.
- Do not hook shell aliases.
- Do not filter arbitrary commands.

## 4. Design

### 4.1 Registry

```python
# poor_cli/rtk_lite/__init__.py
from collections.abc import Callable

Filter = Callable[[str], str]
REGISTRY: dict[str, Filter] = {}

def register(command_pattern: str):
    def deco(fn: Filter) -> Filter:
        REGISTRY[command_pattern] = fn
        return fn
    return deco

def apply(command: str, output: str) -> str:
    """Dispatches to the best-matching registered filter. Pass-through if none."""
```

### 4.2 `git_filter.py`

```python
@register("git status")
def filter_git_status(output: str) -> str:
    """
    Reshape the default `git status` into a compact, token-efficient summary.
    Preserve: branch, ahead/behind, file counts per category, first-N changed paths.
    Drop: advisory text ('use "git restore"...'), heading decoration.
    """
```

Target: ~75% fewer tokens on representative output while preserving every changed path.

### 4.3 Bash tool integration

```python
# tools_async.py::bash
def bash(cmd, ...):
    raw = run_subprocess(cmd)
    filtered = rtk_lite.apply(cmd, raw)
    return ToolResult(output=filtered, meta={"rtk_reduction_pct": ...})
```

## 5. Files to create / modify / delete

See header.

## 6. Implementation plan

1. Land `rtk_lite/__init__.py` with registry.
2. Land `git_filter.py` with `git status` filter + 5 fixture tests.
3. Wire into `bash` tool.
4. Add `git diff --stat` and `ls -la` filters.
5. Stretch: `npm install`, `cargo build`.
6. Tests with captured real-world outputs in `tests/fixtures/rtk_lite/*.txt`.
7. `make lint && make test`.

## 7. Testing & acceptance criteria

- `test_git_status_filter_reduces_tokens_by_60_percent_on_fixture`
- `test_git_status_filter_preserves_all_changed_paths`
- `test_unknown_command_passthrough`
- `test_bash_tool_reports_reduction_in_meta`

**Done criterion**
- [ ] Registry works.
- [ ] `git status` shows ≥60% token reduction on fixture.
- [ ] Filter deployment is opt-out via config.

## 8. Rollback / risk

Low. Opt-out via `rtk_lite.enabled = false`. Each filter has an escape path that returns raw output if parsing fails.

## 9. Out-of-scope & boundary

- 🚫 Do not delete `rtk_integration.py` in this PRD (PRD 007 coordinates).
- 🚫 Do not touch Rust.
- 🚫 Do not hook shell aliases.

## 10. Related PRDs & references

- PRD 007 (stub decisions).
- LEARNING.md §2.2, §1.5.
- PAIN-POINTS.md #9.
