# PROPOSAL D — Agent Self-Discovery via `meta.*` Tools

> **Target:** poor-cli v6.4 / backend-only (Python) with optional diag panel wiring.
> **Depends on:** Phases A / B / C landed (commits `6742fa0`, `22d5918`, `9e7dc03`).
> **Estimated effort:** 1–1.5 engineer days.

---

## 1. Philosophical bearings

**Agent-centric.** The agent is the user interface. When context gets compressed
mid-session, the tool manifest can be truncated out of the system prompt — the
agent then "forgets" what tools exist and reverts to guessing. That breaks the
whole premise of Phase B (every plugin integration is a tool). The agent must
always be able to re-hydrate its own capabilities **via tool calls**, not via a
prayer that the system prompt is still intact.

**Token-centric.** Self-discovery costs tokens every time it runs. Counter-balance:
we give the agent terse, paginated, filterable queries so it can discover *what
it needs* rather than dumping the whole registry. The cost of a bad guess (5
wasted tool calls, 2 turns of context) already far exceeds the cost of one
`meta.list_tools` call.

**Not a dashboard.** These tools exist for the agent, not the user. Users have
`:PoorCLIDiag` and `:PoorCLIHelp palette`. We don't wrap meta.* in a UI panel;
we don't add `:PoorCLIMeta *` verbs; we don't expose it as a keybind.

## 2. Anti-scope-creep fences

- **No user-facing `:PoorCLIMeta *` commands.** Tools only.
- **No persistent tool-call history beyond session.** `meta.call_history`
  reads from in-memory state; session end = state gone. Cross-session
  persistence is a different feature (see PROPOSAL-G-FUTURES).
- **No "tool marketplace"** of any kind — no network fetches, no discovery
  of remote tools. The only tools meta.* knows about are those registered
  in the local process.
- **No LLM-based tool selection** inside meta.*. The tools return structured
  data; the agent does the reasoning.
- **No modification of tool definitions via meta.***. Read-only surface.

## 3. End state (definition of success)

Five new tools registered in `poor_cli.tools._registry`:

| Tool | Purpose |
|---|---|
| `meta.list_tools` | Enumerate tools; filter by `domain` prefix and/or free-text `query` |
| `meta.describe_tool` | Get the schema + examples for one tool by name |
| `meta.call_history` | Return recent tool-call records (CallRecords) for the session |
| `meta.health` | Snapshot from `tool_health` — success rates, p50/p95, recent errors |
| `meta.what_changed` | Delta of repo state since session start (files touched by tools, grouped) |

**Hard invariants:**

1. Every meta.* tool returns typed `ContentBlock` lists (no `vim.inspect`-style
   dumps). Schemas are validated by T1.
2. `meta.list_tools({})` (no args) returns ≥ 34 entries (current tool count)
   and does NOT exceed 4000 tokens rendered. If it would, truncate + set
   `metadata.truncated = true` with a pagination cursor.
3. `meta.call_history({n: 20})` returns the last 20 CallRecords (or all, if fewer)
   in chronological order.
4. `meta.health({tool: "git.commit"})` returns the per-tool snapshot from
   `tool_health`. `meta.health({})` returns a summary across all tools with
   `window_s = 3600`.
5. `meta.what_changed({})` returns files touched by poor-cli tools this session
   (distinct from files the user edited) as a `TableBlock`.
6. All five tools appear in `meta.list_tools({})` output (self-discovery is itself
   discoverable).
7. `ctx.call_tool` (T10) works inside meta.* handlers — meta tools can call
   each other without spawning sub-agents.

**Test coverage** ≥ 15 pytest cases across the 5 tools. All green.

## 4. Design notes

### 4.1 Session-scoped state

The dispatcher returns a `CallRecord` per call. Nothing in the current codebase
accumulates these per-session. We need a thin `SessionRecorder` object that the
dispatcher pushes records into and that `meta.call_history` reads from.

**Proposal:** add `poor_cli/session_recorder.py`:

```python
@dataclass
class SessionRecorder:
    records: List[CallRecord] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    _file_writes: Set[str] = field(default_factory=set)  # paths touched by tools

    def record(self, rec: CallRecord, args: dict) -> None:
        self.records.append(rec)
        # Best-effort: some tools mutate files; capture the paths
        # from known-mutating tools so meta.what_changed can surface them.
        if rec.tool in {"git.stage", "git.unstage", "git.commit", "hunks.stage",
                        "hunks.reset", "fs.write", "deploy.run"}:
            for key in ("file", "path", "paths"):
                val = args.get(key)
                if isinstance(val, str):
                    self._file_writes.add(val)
                elif isinstance(val, list):
                    for v in val:
                        if isinstance(v, str):
                            self._file_writes.add(v)
```

**Integration:** the server handler (`chat.py` + friends) instantiates one
`SessionRecorder` per session and passes it through the tool context (`ctx`).
`tool_dispatcher.dispatch_one` calls `ctx.session_recorder.record(...)` after
each dispatch if the attribute is present.

The meta.* handlers read `ctx.session_recorder.records` directly.

### 4.2 Pagination for `meta.list_tools`

If unfiltered `list_tools` would exceed a rendered size budget (default 4000
tokens, roughly 4000 chars × 0.25 tokens/char):

1. Sort tools alphabetically by name.
2. Apply the filter (`domain`, `query`).
3. Render until the token budget is close; emit a final line
   `... N more (use offset=M to continue)`.
4. Set `metadata.next_offset = M` or `null` if done.

Accept `offset` and `limit` args; default `limit = 50` (typically enough for
one domain).

### 4.3 Output shapes

**`meta.list_tools`** → `TableBlock` with columns `name | exclusive | description`
where description is the first sentence of the tool's description (same
truncation as `tool_prompt.manifest_markdown`).

**`meta.describe_tool`** → `CodeBlock(language="markdown", code=<from tool_prompt_gen.describe_registry_tool>)`.
This is the prose description + args + examples.

**`meta.call_history`** → `TableBlock` with columns `tool | outcome | wall_ms | retries | ts`.
The `outcome` column is `ok`, `err`, `timeout`, or `degraded`.

**`meta.health`** → `TableBlock` when no tool specified; `CodeBlock(language="json")` when one tool is specified
(full snapshot).

**`meta.what_changed`** → `TableBlock` with columns `file | first_touched_by | touches`.

## 5. Files expected to be touched

```
poor_cli/tools/meta.py                            NEW (~300 LOC)
poor_cli/tools/__init__.py                        MOD (add `from . import meta`)
poor_cli/session_recorder.py                      NEW (~80 LOC)
poor_cli/tool_dispatcher.py                       MOD (~20 LOC — record at dispatch end)
poor_cli/server/handlers/chat.py                  MOD (~10 LOC — instantiate + pass to ctx)
poor_cli/server/handlers/common.py                MOD (~5 LOC — add _session_recorder field)
tests/test_meta_tools.py                          NEW (~250 LOC, ≥ 15 cases)
```

## 6. Test specification

```python
# tests/test_meta_tools.py outline

def test_list_tools_contains_all_registered():
    # Call meta.list_tools({}); assert 34+ rows, including every core tool.

def test_list_tools_filters_by_domain():
    # domain="git" → only git.* rows

def test_list_tools_filters_by_query():
    # query="commit" → git.commit matches

def test_list_tools_paginates_when_budget_exceeded():
    # Register 500 fake tools; call with default limit; assert truncated.

def test_describe_tool_includes_schema_and_examples():
    # Build a fake tool with examples; describe_tool returns CodeBlock with
    # "Arguments:" and "Examples:" sections.

def test_describe_tool_unknown_name():
    # Returns is_error=True with unknown_tool=True metadata.

def test_call_history_records_in_order():
    # Dispatch 3 tools; call_history returns 3 rows in chronological order.

def test_call_history_respects_n_limit():
    # Dispatch 5; n=2 → 2 most recent.

def test_call_history_filters_by_tool_name():
    # tool_filter="git.status" → only that tool's calls.

def test_health_returns_per_tool_snapshot():
    # Record 5 successes + 2 failures for git.status; snapshot has
    # successes=5, failures=2.

def test_health_all_tools_summary():
    # meta.health({}) → TableBlock with one row per recorded tool.

def test_what_changed_tracks_mutating_tools():
    # Dispatch git.stage with paths=["a.py", "b.py"]; what_changed shows
    # a.py and b.py as touched.

def test_what_changed_empty_at_start():
    # Fresh session → "no changes yet" TextBlock.

def test_meta_tools_self_discoverable():
    # list_tools({}) includes meta.list_tools, meta.describe_tool, etc.

def test_meta_tools_can_call_each_other_via_ctx():
    # A fake wrapper tool calls ctx.call_tool("meta.list_tools", {}) and
    # composes its output; depth limit respected.

def test_session_recorder_is_independent_per_session():
    # Two SessionRecorder instances don't leak records.
```

## 7. Known risks

| Risk | Mitigation |
|---|---|
| `meta.list_tools` output explodes with Phase-B tool additions | Pagination + token budget + `domain` filter encourage scoped queries. |
| `SessionRecorder` grows unboundedly for long sessions | Cap `records` at 1000 entries (ring buffer); older records evict. |
| `what_changed` lies when tools mutate paths not in their args (e.g. `task.run` spawning `make build`) | Accept the limitation. Document: "tracks paths declared in tool args, not side effects." |
| Circular calls via `ctx.call_tool("meta.list_tools", ...)` inside a meta tool | T10's depth cap (3) already covers this. |

## 8. Done when

- [ ] All 5 meta.* tools registered and discoverable via `meta.list_tools({})`
- [ ] `SessionRecorder` wired through ctx; dispatcher records every call
- [ ] 15+ new pytest tests green
- [ ] `meta.list_tools({})` rendered output stays under 4000 tokens (measured)
- [ ] Manual E2E: open a chat, run `git.status`, ask agent "what did you just do" — agent calls `meta.call_history({n: 1})` and reports it

## 9. Out of scope

- Cross-session tool call logs (see PROPOSAL-G-FUTURES, "Persistent tool history")
- User-facing UI for browsing tools (`:PoorCLIHelp palette` already exists)
- Rate limits / permissions on meta.* (they're read-only; global `permission_mode = prompt` already gates tool calls)
- Semantic tool routing (see PROPOSAL-E-FRUGALITY)
