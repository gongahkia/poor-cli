# PROPOSAL B — Every Feature Flows Through the Agent

> **Target:** `poor-cli` v6.3 / cross-cutting backend + frontend change.
> **Scope:** `poor_cli/tools/**` (new + modified), `poor_cli/server/handlers/**`, `nvim-poor-cli/lua/poor-cli/integrations/**`, chat system-prompt template.
> **Depends on:** Phase A (command collapse) landed; Phase C (tool-calling robustness) landing in parallel — Proposal B does not require all of C's features but benefits strongly from T1 (strict schemas), T6 (graceful degradation), T11 (typed result blocks).
> **Estimated effort:** 4–6 engineer days.

---

## 1. Context

After Phase A the user sees 9 commands, but the plugin still contains ~a dozen integrations (neogit, DAP, trouble, gitsigns, oil, overseer, deploy tooling, service tooling, watch directives) that each function as **plugin proxies** — `:PoorCLIReview commit` opens neogit for you, `<leader>pb` toggles a DAP breakpoint, etc. From the user's perspective, this makes poor-cli feel like an aggregator: a bag of shortcuts to other plugins. The question "why use poor-cli instead of the plugin directly?" has no clean answer.

Phase B reframes every integration: **the agent is the consumer** of these plugins. The user talks to the agent in chat; the agent decides when to invoke neogit, DAP, trouble, etc. via typed tool calls; the plugin is a rendering surface and a mechanical effect. Poor-cli becomes a tool that *uses* these plugins as part of its reasoning loop, not a launcher that opens them.

## 2. End state (definition of success)

**Hard invariants:**

1. For every integration listed in §5, there are ≥1 tools registered in the backend tool registry (`poor_cli/tool_registry_builder.py`).
2. No user-facing `:PoorCLI*` verb directly invokes a plugin-integration side effect. Verbs either (a) mutate agent state, (b) render existing data, or (c) send a chat message. Plugin effects flow only through `tool_dispatch`.
3. The agent's system prompt / tool manifest includes a description + schema for every new tool.
4. End-to-end test: starting from a chat message like "commit the current diff with a conventional message", the agent calls `git.commit` → neogit writes the commit. No user keypress required beyond `<CR>` on the chat input.
5. When an integration's underlying plugin is missing (e.g. neogit not installed), the corresponding tool degrades to raw CLI (`git commit`) and reports the fallback to the agent. **No tool returns a plugin-missing error to the user.**
6. Every tool call is visible in the Timeline panel with its structured result (not `vim.inspect` dump).

## 3. Taxonomy of changes

Each integration gets:
- **N tools** registered in the backend with JSONSchema arg schemas.
- **A Lua bridge** that the tool calls into via JSON-RPC notification (for read ops) or request (for write ops that need to wait).
- **Removed user-facing command(s)** if those commands only existed to launch the plugin.
- **Retained user-facing views** if the plugin surfaces a panel the user wants to see (e.g. Trouble window for browsing AI-emitted diagnostics).

Tools are named `<domain>.<verb>` (e.g. `git.commit`, `debug.breakpoint.set`, `fs.browse`). The `.` separator groups related tools in the registry listing and in diag/timeline views.

## 4. Tool registration mechanics

### 4.1 Backend tool registration

`poor_cli/tool_registry_builder.py` already exposes `register(name, schema, handler, description)`. Each new tool adds one entry:

```python
from poor_cli.tool_registry_builder import register

register(
    name="git.commit",
    description=(
        "Create a git commit on the current branch. If neogit is available "
        "in the user's Neovim session, the commit UI is opened with the "
        "message prefilled; otherwise this runs `git commit` directly."
    ),
    schema={
        "type": "object",
        "required": ["message"],
        "properties": {
            "message": {"type": "string", "description": "Commit message, first line is the subject."},
            "auto_stage": {"type": "boolean", "default": False},
            "amend": {"type": "boolean", "default": False},
        },
        "additionalProperties": False,
    },
    handler=handle_git_commit,  # async def handler(ctx, args) -> ToolResult
)
```

Handlers return a `ToolResult` dataclass (see Proposal C T11) — typed content blocks rather than raw strings.

### 4.2 Lua bridge

Backend handlers invoke Lua-side effects via RPC **notifications** (fire-and-forget for UX, e.g. "open neogit") or **requests** (when result is needed, e.g. "return list of current DAP breakpoints"). Add notification handlers under `nvim-poor-cli/lua/poor-cli/integrations/<name>_bridge.lua`. Example:

```lua
-- integrations/neogit_bridge.lua
local M = {}
local rpc = require("poor-cli.rpc")

function M.open_commit_message(params)
    local ok, neogit = pcall(require, "neogit")
    if not ok then return end  -- backend will fall back to CLI
    neogit.open({ kind = "commit" })
    -- prefill message
    vim.defer_fn(function()
        local buf = vim.fn.bufnr("NeogitCommitMessage")
        if buf > 0 then
            vim.api.nvim_buf_set_lines(buf, 0, 0, false,
                vim.split(params.message or "", "\n", { plain = true }))
        end
    end, 100)
end

function M.setup()
    rpc.register_notification_handler("integration.neogit.openCommit", M.open_commit_message)
end

return M
```

The bridge modules are loaded from `init.lua::setup()`; their `setup()` functions register RPC handlers during plugin startup.

### 4.3 Capability discovery

At plugin startup the Lua bridge sends `client.capabilities` to the backend enumerating which plugins are present (neogit, dap, trouble, etc.). The backend stores this per-session and uses it to:

- Decide whether to advertise plugin-dependent tools to the model vs. raw-CLI fallback tools.
- Pick the right code path inside a tool handler.

`poor-cli/initialize` RPC already exists; extend its request body to include `clientCapabilities = { neogit = true, dap = false, ... }`. Add logic in `poor_cli/server/runtime.py` to stash it on the session.

---

## 5. Integration-by-integration plan

### 5.1 Neogit — git tooling

**New tools:**

| Tool | Purpose |
|---|---|
| `git.status` | Return structured status (staged/unstaged/untracked lists). Falls back to `git status --porcelain`. |
| `git.diff` | Return diff for a file or the whole repo. Accepts `staged: bool`. |
| `git.stage` | Stage path(s). Prefers neogit staging if available (for visual feedback); else `git add`. |
| `git.unstage` | Converse. |
| `git.commit` | Commit with message; opens neogit commit buffer with prefill if available, else `git commit -m`. |
| `git.log` | Last N commits on current branch, structured. |
| `git.branch.list/create/checkout` | Branch ops. |
| `git.push` | Push with structured auth handling. **Permission-gated by default.** |

**Lua bridge:** `integrations/neogit_bridge.lua` (new).

**Removed user verbs:** `:PoorCLIReview commit` goes away as a direct command; it becomes a slash shortcut `:PoorCLIChat send /commit` which sends the message that the agent interprets as "call `git.commit` after drafting a message".

**Retained user-facing surfaces:** the Neogit commit buffer (when it opens) is neogit's own UI — we don't own that.

**Tests:**
- `tests/test_git_tools.py` — mock subprocess, assert `git.commit` dispatches `git commit -m <msg>` when neogit unavailable.
- `tests/test_git_tools.py::test_neogit_fallback_when_missing` — `clientCapabilities.neogit = False`, assert CLI path taken.
- `nvim-poor-cli/tests/neogit_bridge_spec.lua` — exists; add case for `integration.neogit.openCommit` notification.

### 5.2 DAP — debug tooling

**New tools:**

| Tool | Purpose |
|---|---|
| `debug.session.start` | Start a DAP launch configuration by name. |
| `debug.session.stop` | Terminate. |
| `debug.breakpoint.set` | Args: `{file, line, condition?}`. |
| `debug.breakpoint.clear` | |
| `debug.step.{over,in,out}` | |
| `debug.continue` | |
| `debug.stack` | Return current stack frames, scopes, variables (snapshot). |
| `debug.eval` | Evaluate expression in active frame. |

**Lua bridge:** `integrations/dap_bridge.lua` (exists; extend with read/write RPC handlers). All DAP calls go through `nvim-dap`'s Lua API. Tools request current state via RPC; write tools call `dap.set_breakpoint`, `dap.continue`, etc.

**Removed user verbs:** the `<leader>pb`, `<leader>pB` keybinds go away from default keymaps. Users who want direct DAP control use `nvim-dap` itself; users working through the agent just say "set a breakpoint at line 42 of foo.py".

**Retained surfaces:** `nvim-dap`'s own UI (if the user loads it independently). We don't force-load it.

**Tests:**
- `tests/test_debug_tools.py::test_breakpoint_set_sends_rpc`.
- `tests/test_debug_tools.py::test_eval_returns_structured_result`.
- `nvim-poor-cli/tests/dap_bridge_spec.lua` — extend with breakpoint-set RPC test.

### 5.3 Trouble — diagnostics tooling

**New tools:**

| Tool | Purpose |
|---|---|
| `diagnostics.list` | Args: `{buffer?, severity?}`. Returns LSP + AI diagnostics snapshot. |
| `diagnostics.emit` | Agent emits a diagnostic visible to the user (highlighted code span + message). Surfaces in Trouble window under source `poor-cli`. |

**Lua bridge:** `integrations/trouble_bridge.lua` (new) + existing `trouble_source.lua`. Agent-emitted diagnostics are stored in `vim.diagnostic` under namespace `poor-cli`.

**Removed user verbs:** `:PoorCLIDiag trouble` stays (it's a utility for the user to open the Trouble window). But the user can't use it to "browse AI suggestions" unless the agent actually emitted some.

**Tests:**
- `tests/test_diagnostics_tools.py`.
- `nvim-poor-cli/tests/trouble_source_spec.lua` — exists; extend.

### 5.4 Gitsigns — hunk-level tooling

**New tools:**

| Tool | Purpose |
|---|---|
| `hunks.list` | Args: `{file}`. Returns per-hunk diff data. |
| `hunks.stage` | Args: `{file, hunk_index}`. |
| `hunks.reset` | |
| `hunks.ai_mark` | Tag a hunk as AI-authored (drives the ✱ glyph). |

**Lua bridge:** `integrations/gitsigns_bridge.lua` (expand existing module). Read ops query gitsigns; write ops call into gitsigns' `actions` API. Falls back to `git diff` parsing if gitsigns missing.

**Removed user verbs:** none — gitsigns integration was never user-facing (just visual glyph).

**Tests:**
- `tests/test_hunk_tools.py`.
- `nvim-poor-cli/tests/gitsigns_bridge_spec.lua` — exists; extend.

### 5.5 Oil — filesystem browse

**New tools:**

| Tool | Purpose |
|---|---|
| `fs.browse` | Args: `{path, max_depth?}`. Returns directory tree (respecting .gitignore). Uses oil.nvim's file-tree if available for consistency with user's own oil buffer. |
| `fs.read` | (This is probably already a core tool — don't duplicate.) |
| `fs.glob` | Args: `{pattern}`. Fast glob. |

**Lua bridge:** `integrations/oil_bridge.lua` (new). Oil integration is cosmetic — the tool itself uses `vim.fn.readdir` server-side. The bridge is optional.

**Removed user verbs:** none.

**Tests:**
- `tests/test_fs_browse_tool.py`.

### 5.6 Overseer — task runner

**New tools:**

| Tool | Purpose |
|---|---|
| `task.run` | Args: `{name, args?, cwd?}`. Runs a named task. Uses overseer.nvim's task template if available for consistency (user sees task in their overseer UI); else spawns subprocess. |
| `task.list` | List available task templates. |
| `task.status` | Args: `{task_id}`. |
| `task.logs` | Args: `{task_id, tail_lines?}`. |
| `task.cancel` | |

**Lua bridge:** `integrations/overseer_bridge.lua` (extend existing). The backend's task registry stores the mapping `task_id → {overseer_handle?, subprocess_pid?}` so cancel/logs route to the right place.

**Removed user verbs:** `:PoorCLIDiag service-*` (from Phase A) — services are just long-running tasks; merge into `task.*`. Also `:PoorCLIAgent task-{inbox,runs}` stays as a user-facing view of task history.

**Tests:**
- `tests/test_task_tools.py`.
- `nvim-poor-cli/tests/overseer_bridge_spec.lua` — exists; extend.

### 5.7 Deploy — project deployment

**New tools:**

| Tool | Purpose |
|---|---|
| `deploy.run` | Args: `{target, dry_run?}`. Reads `poor-cli.deploy.yaml` (new config file) or `.poor-cli/deploy.json` for the deploy command per target, runs it. |
| `deploy.preview.start` | Background dev server. |
| `deploy.preview.stop` | |
| `deploy.preview.status` | |
| `deploy.history` | Last N deploys. |

**Lua bridge:** minimal — deploy runs server-side; Lua just surfaces progress via notifications.

**Removed user verbs:** `:PoorCLIDeploy *` already removed in Phase A (§4.10). This proposal only adds the agent-callable tools.

**Tests:**
- `tests/test_deploy_tools.py` — mock the configured command, assert subprocess spawned.

### 5.8 Watch — `@poor-cli` directives

**New tools:**

| Tool | Purpose |
|---|---|
| `watch.directives.list` | Return all pending `// @poor-cli: <instruction>` directives found in the repo. |
| `watch.directives.consume` | Args: `{file, line}`. Mark a directive as acted-on. |

**Lua bridge:** `watch_panel.lua` keeps its read-only user view. Write semantics come from the tools.

**Agent behavior:** on every chat turn where the user doesn't explicitly override, the system prompt instructs the agent to check `watch.directives.list` and proactively address any pending directives. Agent invokes `watch.directives.consume` after acting on each.

**Tests:**
- `tests/test_watch_tools.py`.

### 5.9 Review — code review scaffolding

**New tools:**

| Tool | Purpose |
|---|---|
| `review.pr` | Args: `{number, repo?}`. Fetch PR metadata + diff, return structured. |
| `review.lint` | Args: `{file?}`. Runs configured linters and returns findings. |
| `review.changes` | Return diff of current changes vs. HEAD. |

**User verbs kept:** `:PoorCLIReview pr`, `:PoorCLIReview lint`, `:PoorCLIReview file` remain — they're shortcuts that send a pre-scripted chat message like "review PR 42 using the review.pr tool". The verb does not directly invoke the review logic; it just seeds a prompt.

**Tests:**
- `tests/test_review_tools.py`.

---

## 6. System prompt update

The agent's system prompt (`poor_cli/prompts/system.py` or wherever the base prompt template lives) must advertise the new tools. The existing tool manifest mechanism (each tool's `description` is concatenated into the system prompt) should handle this automatically if Proposal C's T12 (auto-generated descriptions) is landed. Until then, hand-write a one-paragraph block per tool family:

```
### git
You have tools to inspect and modify the git repository: `git.status`,
`git.diff`, `git.stage`, `git.unstage`, `git.commit`, `git.log`,
`git.branch.{list,create,checkout}`, `git.push`. Prefer calling these
over asking the user to run git commands manually. `git.push` is
permission-gated; the user may need to approve.
```

Repeat per family (debug, diagnostics, hunks, fs, task, deploy, watch, review).

## 7. Capability negotiation schema

At plugin startup, the Lua client sends:

```json
{
  "method": "initialize",
  "params": {
    "clientCapabilities": {
      "neovim": { "version": "0.12.1" },
      "plugins": {
        "neogit": true,
        "nvim-dap": true,
        "trouble.nvim": true,
        "gitsigns.nvim": true,
        "oil.nvim": false,
        "overseer.nvim": false,
        "snacks.nvim": true
      }
    }
  }
}
```

The backend stores this on the session object. Tool handlers read `ctx.session.capabilities.plugins[name]` to choose the code path.

Add to `nvim-poor-cli/lua/poor-cli/rpc.lua::initialize()` — detect each optional plugin via `pcall(require, name)` and pass the table through.

## 8. Implementation plan

### Phase B.1 — Scaffolding
1. Extend `initialize` RPC with `clientCapabilities.plugins`. Lua side detects and sends. Backend stores on session.
2. Define `ToolResult` dataclass (if Proposal C not landed): `@dataclass ToolResult(content: list[ContentBlock], is_error: bool = False, metadata: dict = {})`.
3. Add `integrations/<name>_bridge.lua` stubs with `M.setup()` registering notification handlers (empty bodies for now).

### Phase B.2 — git tools (reference implementation)
1. Write `poor_cli/tools/git.py` with `git.status`, `git.diff`, `git.commit`, etc.
2. Wire `neogit_bridge.lua::open_commit_message`.
3. Add `git.push` permission rule (`git.push: prompt` by default) to the default policy.
4. Land `tests/test_git_tools.py` and `nvim-poor-cli/tests/neogit_bridge_spec.lua` additions.
5. Smoke test: chat "commit this with a conventional message" → tool fires → commit created.

### Phase B.3 — debug + diagnostics + hunks
Replicate B.2 pattern for DAP, Trouble, Gitsigns.

### Phase B.4 — fs + task + deploy
Same.

### Phase B.5 — watch + review
Same; integrate `watch.directives.list` into the default agent-turn preflight.

### Phase B.6 — cleanup
- Remove direct-invocation keybinds from `keymaps.lua` (e.g. `<leader>pb` DAP) where they duplicate a tool.
- Update `README.md` — "poor-cli uses your plugins as tools" section.
- MIGRATION.md v6.3 rename table covers the removed `:PoorCLIReview commit` direct-launch (now agent-driven).

## 9. Files created

```
poor_cli/tools/
  git.py
  debug.py
  diagnostics.py
  hunks.py
  fs.py
  task.py
  deploy.py
  watch.py
  review.py
nvim-poor-cli/lua/poor-cli/integrations/
  neogit_bridge.lua
  dap_bridge.lua                 (extend existing)
  trouble_bridge.lua
  gitsigns_bridge.lua            (extend existing)
  oil_bridge.lua
  overseer_bridge.lua            (extend existing)
tests/
  test_git_tools.py
  test_debug_tools.py
  test_diagnostics_tools.py
  test_hunk_tools.py
  test_fs_browse_tool.py
  test_task_tools.py
  test_deploy_tools.py
  test_watch_tools.py
  test_review_tools.py
  test_e2e_agent_tool_flow.py    (end-to-end)
```

## 10. End-to-end test (mandatory)

`tests/test_e2e_agent_tool_flow.py`:

```python
def test_agent_commit_flow(mock_provider, tmp_git_repo):
    """
    Prove that a chat message "commit with a conventional message"
    causes the agent to call git.commit without user keypresses.
    """
    # arrange
    session = start_session(workdir=tmp_git_repo)
    mock_provider.next_response_calls_tool(
        tool="git.commit",
        args={"message": "feat: initial commit"},
    )

    # act
    response = session.chat("commit with a conventional message")

    # assert
    assert "commit" in response.lower()
    log = subprocess.run(["git", "log", "-1", "--format=%s"],
                         cwd=tmp_git_repo, capture_output=True, text=True).stdout.strip()
    assert log == "feat: initial commit"
    assert session.tool_calls == [("git.commit", {"message": "feat: initial commit"})]
```

## 11. Known risks

| Risk | Mitigation |
|---|---|
| Users lose muscle memory for `<leader>pb` etc. | `MIGRATION.md` v6.3 section lists each removed keybind + its new "ask the agent" phrasing. |
| Tool registry bloats to 40+ tools, model struggles to pick the right one | Group tools by domain prefix (`git.*`, `debug.*`); system prompt instructs agent to filter by prefix first. |
| Plugin-capability detection races with tool invocation | Initialization is synchronous before any chat turn is accepted; tool handlers can trust `ctx.session.capabilities`. |
| A plugin API changes (neogit major version) | Bridge modules have a one-file blast radius; fix in one place. |
| Fallback code paths for every plugin double maintenance | Accept it. The fallbacks are the real tool; the plugin integration is the nicety. |

## 12. Done when

- 9 integration families each have ≥1 tool, a bridge module, tests, and zero user-facing direct-launch commands (unless the launch is a scripted chat message).
- `test_e2e_agent_tool_flow.py` passes for git, debug, and task families.
- Every tool has a JSONSchema (validated if T1 landed).
- System prompt lists every new tool family.
- `make test` (Python) and `make test-lua` both green.
- MIGRATION.md v6.3 rename table complete.
