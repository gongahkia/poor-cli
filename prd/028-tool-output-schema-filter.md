# PRD 028: Per-tool schema-declared output filter

- **Wave:** 2
- **Status:** ready
- **Owner (human):** @gongahkia
- **Estimated effort:** medium (1w + per-tool tuning)
- **Blocks:** —
- **Blocked by:** —
- **Files it mutates:**
  - `poor_cli/tool_output_filter.py`
  - `poor_cli/tools_async.py` (add filter declarations to tools)
- **New files it adds:**
  - `tests/test_tool_output_schema_filter.py`

## 1. Problem

Every tool dumps full output into context. MCP responses bloat by nature (PAIN-POINTS.md #2). LEARNING.md §2.2: "Tools declare JSONPath fields worth keeping; filter strips the rest before the model sees it."

## 2. Current state

`tool_output_filter.py` exists with JSONPath capability but is opt-in per call. No per-tool defaults.

## 3. Goal & non-goals

**Goal:** every built-in tool declares its output-shape filter (via JSONPath for JSON tools, regex or keep-lines for text tools). The dispatcher applies the filter post-execution, pre-context. Users see a "filtered from X KB to Y KB" note in the timeline.

**Non-goals:**
- Do not filter user-inspected output (full output still visible in timeline expand).
- Do not filter MCP tools (server owns their schemas — that's a PRD 024 follow-up).

## 4. Design

### 4.1 Tool declaration

```python
@tool(name="git_status", output_filter=GitStatusFilter())
async def git_status(...): ...
```

### 4.2 Filter protocol

```python
class OutputFilter(Protocol):
    def apply(self, raw: str) -> FilterResult:
        """Returns compacted output + stats."""

@dataclass
class FilterResult:
    output: str
    original_size: int
    filtered_size: int
    dropped_paths: list[str]
```

### 4.3 Built-in filters

- `gh_pr_view` → keep `number, title, state, labels, assignees, body, latestReviewDecision`; drop everything else.
- `git_log` → keep hash, author_short, date, subject.
- `gh_issue_list` → keep number, title, state, labels, author.
- `dependency_inspect` → drop transitive deps unless asked.

### 4.4 Full output retained in timeline

Timeline (PRD 015) can request full output via `poor-cli/toolFullOutput` for expansion.

## 5. Files to create / modify / delete

See header.

## 6. Implementation plan

1. Add declaration syntax to the `@tool` decorator.
2. Add filter protocol + built-in filters.
3. Wire into `tool_dispatch` post-execution hook.
4. Expose full output via RPC.
5. Tests with fixture outputs.
6. `make lint && make test`.

## 7. Testing & acceptance criteria

- `test_git_status_default_filter_drops_advisory_text`
- `test_filter_stats_populated`
- `test_full_output_retrievable_via_rpc`

**Done criterion**
- [ ] Every mutating/read tool has a declared filter.
- [ ] Default filters reduce token count measurably.
- [ ] Full output still reachable.

## 8. Rollback / risk

Low. Per-tool opt-out.

## 9. Out-of-scope & boundary

- 🚫 Do not touch MCP tool outputs.
- 🚫 Do not change `tool_output_filter.py` API beyond what's needed.

## 10. Related PRDs & references

- PRD 015 (timeline full-output expansion).
- PRD 024 (MCP).
- LEARNING.md §2.2. PAIN-POINTS.md #2.
