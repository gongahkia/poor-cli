# Phase C — Orchestration

**Goal:** make the harness composable. User defines agents in markdown; the harness can run long agents detached; permissions are expressed in a real DSL instead of ad-hoc lists.

**Order (commit each separately):**
1. Markdown-defined subagents (`.poor-cli/agents/<name>.md`)
2. Async detached background runs
3. Per-tool permission rule DSL

**Cross-cutting rules:**
- One commit per feature.
- Run full pytest after each.
- Phase B's edit-staging applies to subagents too — no special-case bypass.
- Per-tool DSL replaces nothing; it sits beside the existing `permission_rules.py` engine and is composed at evaluation time.

**Dependencies on Phase A & B:** uses A3 hooks (`subagent_start`/`subagent_stop`), uses A1 HUD to show detached run state, uses B3 staging for safety in subagent edits.

---

## C1 — Markdown-defined subagents

### Goal
Drop a markdown file into `.poor-cli/agents/<name>.md` to define a subagent: system prompt, allowed tools, model override, budget, archetype. Mirrors Claude Code's pattern. The harness loads them at startup and exposes them as targets for `delegate_task`.

### Verified anchors
- `poor_cli/sub_agent.py` — `SubAgentArchetype` enum with `GENERIC|RESEARCH|CODE|TEST|REVIEW|ADVISOR`. `_ARCHETYPE_CONFIGS` dict with `allowed_tools` + `system_prompt` per archetype. `_hard_denied_tools = {"delegate_task", "spawn_parallel_agents"}`.
- `poor_cli/skills.py` + `poor_cli/skills/*.md` — existing markdown loader; reuse the parsing pattern.
- `poor_cli/_tool_registry_builder.py` — `delegate_task` tool; needs to accept new agent names.

### Files to create
- `poor_cli/agent_definitions.py` — loader + registry.
- `poor_cli/cli/agent_cmds.py` — `poor-cli agent list|show|run|validate`.
- `tests/test_agent_definitions.py`.
- Sample definitions:
  - `.poor-cli/agents/researcher.md`
  - `.poor-cli/agents/security-reviewer.md`

### Files to modify
- `poor_cli/sub_agent.py` — accept a custom `AgentDefinition` in addition to enum-based archetypes; resolve allowed-tools and system prompt from definition when provided.
- `poor_cli/_tool_registry_builder.py` — `delegate_task` tool schema accepts `{archetype: string, agent?: string, prompt: string, ...}`. If `agent` is provided, look it up in the registry.
- `poor_cli/cli_app.py` — wire `poor-cli agent ...` verb (mirror existing verb wiring style).

### Markdown schema

```markdown
---
name: security-reviewer
description: Reviews diff for OWASP top-10 issues; read-only.
model: claude-sonnet-4-20250514
provider: anthropic
budget:
  max_thinking_tokens: 8192
  max_output_tokens: 2048
allowed_tools:
  - read_file
  - grep_files
  - git_diff
  - git_log
  - semantic_search
denied_tools:
  - write_file
  - run_shell
hooks:
  pre_run: ".poor-cli/agents/hooks/sec-pre.sh"
---

# System prompt

You are a security review subagent. Look only for:
- Injection (SQL, shell, template).
- Auth/authz mistakes.
- Secret leakage.
- Unsafe deserialization.

Return a JSON-shaped finding list. Prefer no false positives.
```

### Loader

```python
# poor_cli/agent_definitions.py
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class AgentDefinition:
    name: str
    description: str
    system_prompt: str
    model: Optional[str] = None
    provider: Optional[str] = None
    allowed_tools: Optional[List[str]] = None
    denied_tools: List[str] = field(default_factory=list)
    max_thinking_tokens: int = 4096
    max_output_tokens: int = 4096
    hooks: Dict[str, str] = field(default_factory=dict)
    source_path: str = ""

    def to_dict(self) -> Dict[str, Any]: ...


class AgentDefinitionRegistry:
    """Loads .poor-cli/agents/*.md and exposes them by name."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root.resolve()
        self.agents_dir = self.repo_root / ".poor-cli" / "agents"
        self._defs: Dict[str, AgentDefinition] = {}
        self._errors: List[Dict[str, Any]] = []
        self.reload()

    def reload(self) -> None: ...
    def get(self, name: str) -> Optional[AgentDefinition]: ...
    def list(self) -> List[AgentDefinition]: ...
    def errors(self) -> List[Dict[str, Any]]: ...

    @staticmethod
    def parse(path: Path) -> AgentDefinition: ...   # YAML frontmatter + markdown body
```

YAML frontmatter parsing: use stdlib `yaml` already in deps (PyYAML). Body after `---\n...---\n` is the system prompt.

### Validation rules
- `name` must match regex `^[a-z][a-z0-9-]{1,40}$` and equal the filename stem.
- `allowed_tools` if present must be a subset of currently registered tools (validate against `_tool_registry_builder` snapshot).
- `denied_tools` always wins over `allowed_tools`.
- The hard-deny set from `sub_agent.py` (`delegate_task`, `spawn_parallel_agents`) is always denied for custom agents.

### CLI

```
poor-cli agent list                   # name, description, source path
poor-cli agent show <name>            # full definition
poor-cli agent validate               # parse all, exit non-zero on errors
poor-cli agent run <name> --prompt "..."   # one-shot detached run via task_manager
```

### Test plan
`tests/test_agent_definitions.py`:
- Round-trip parse of the two sample definitions.
- Invalid frontmatter records an error and skips registration.
- Tool whitelist intersection with hard-deny works.
- Name regex enforcement.

### Commit
```
feat(agents): markdown-defined subagents in .poor-cli/agents/

Adds AgentDefinitionRegistry that loads agent specs from
.poor-cli/agents/*.md (YAML frontmatter + markdown system prompt).
sub_agent.py honors per-definition tool whitelist, denied tools,
model/provider overrides, and per-turn budget caps. delegate_task
tool accepts {agent: <name>}. New `poor-cli agent` verb for
list/show/validate/run.
```

### Acceptance
- Two sample definitions load and pass `poor-cli agent validate`.
- `delegate_task` to a custom agent runs with the configured tools only.
- Pytest green.

---

## C2 — Async detached background runs

### Goal
Long-running agent runs that survive TUI exit. Operator can launch, list, watch, and cancel them. Builds on `task_manager.py` (already declares "background execution" in the module docstring) but exposes it as a first-class CLI surface and TUI panel.

### Verified anchors
- `poor_cli/task_manager.py` — has `APPROVAL_REQUIRED_PRESETS = {"workspace-write", "full-access"}`. Already supports isolated worktrees per task per docstring.
- `poor_cli/run_history.py` — already records run metadata.
- `poor_cli/cli/state_cmds.py` and `poor_cli/cli/__init__.py` — pattern for CLI verbs.
- `.poor-cli/` directory convention for repo-local state.

### Files to create
- `poor_cli/cli/task_cmds.py` — `poor-cli task run|list|watch|cancel|inspect|prune`.
- `poor_cli/task_supervisor.py` — long-running supervisor process.
- `poor_cli/server/handlers/tasks_async.py` — RPC `poor-cli/taskRunDetached`, `poor-cli/taskWatch` (streaming), `poor-cli/taskCancel`.
- `tests/test_task_supervisor.py`.

### Files to modify
- `poor_cli/task_manager.py` — add `spawn_detached(task_id, ...)`, `attach_to(task_id)` (yields stream), `cancel(task_id)`. Use `subprocess.Popen` with `start_new_session=True` (POSIX) so the child outlives the parent shell.
- `poor_cli/cli_app.py` — wire `poor-cli task ...` verb (router pattern; existing modes already include task).
- `poor_cli/tui/textual_app.py` — add a `/tasks` slash command opening a side panel listing running detached tasks; allow cancellation.

### Spawn architecture

Each detached task:
1. Allocates a worktree under `.poor-cli/tasks/<id>/worktree/` (already pattern in `task_manager.py`).
2. Writes a `task.json` with config (prompt, provider, model, budget, sandbox preset).
3. Forks a `python3 -m poor_cli.task_supervisor --task-id <id>` process with `start_new_session=True`, redirecting stdout/stderr to `.poor-cli/tasks/<id>/log.ndjson`.
4. Records pid in `.poor-cli/tasks/<id>/pid` and removes on exit.
5. Stream is reconstructed by tailing `log.ndjson`; `poor-cli task watch <id>` opens a tail follower; TUI reads via the streaming RPC.

### CLI

```
poor-cli task run --prompt "..." --provider anthropic --detach    # prints task id
poor-cli task list                                                 # id, status, started, pid, last event
poor-cli task watch <id>                                           # follow log.ndjson
poor-cli task cancel <id>                                          # SIGTERM then SIGKILL on grace timeout
poor-cli task inspect <id>                                         # full task.json + last 50 events
poor-cli task prune --status completed --older-than 7d
```

### Safety
- Default sandbox preset for detached runs is `read-only` unless `--preset workspace-write` is passed AND the policy permits it (mirror `APPROVAL_REQUIRED_PRESETS` enforcement).
- Detached runs MUST honor edit-staging from B3 unless `--auto-approve-edits` is passed; CI usage requires `--auto-approve-edits` since no operator is present.

### Hook events
- Fire `task_started` (existing) and `task_finished` (existing) — no new events needed.
- `subagent_start`/`subagent_stop` (A3) fire if the detached run spawns subagents.

### Test plan
`tests/test_task_supervisor.py`:
- `spawn_detached` returns task id and writes pid file.
- Supervisor child writes log lines tail-able via `attach_to`.
- `cancel` sends SIGTERM, waits, then SIGKILL.
- `prune` removes only matching task dirs.
- Avoid actually spawning real LLM calls — mock provider.

### Commit
```
feat(tasks): async detached background runs survive TUI exit

Adds task_supervisor.py + `poor-cli task run --detach` + watch/cancel/
inspect/prune. Each task gets isolated worktree + ndjson log tail.
Default sandbox is read-only; CI mode (--auto-approve-edits) bypasses
diff approvals. Existing task_started/task_finished hooks fire on
spawn and exit.
```

### Acceptance
- `poor-cli task run --detach --prompt "ls"` returns id and exits.
- `poor-cli task list` shows the task.
- `poor-cli task watch <id>` tails events.
- Pytest green.

---

## C3 — Per-tool permission rule DSL

### Goal
Replace ad-hoc allow/deny lists with a small declarative DSL stored in `.poor-cli/permissions.yml`. Composable with the existing `permission_rules.py` engine; existing rules continue to work.

### Verified anchors
- `poor_cli/permission_rules.py` — `PermissionRule`, `PermissionRuleEngine`, scopes: user/project/local/session.
- `poor_cli/permission_engine.py` — central evaluator (read for shape, do not break callers).
- `poor_cli/repo_config.py` — config loader; can host pointer to permissions file.

### Files to create
- `poor_cli/permission_dsl.py` — parser + evaluator.
- `tests/test_permission_dsl.py`.
- Sample `.poor-cli/permissions.example.yml`.

### Files to modify
- `poor_cli/permission_engine.py` — at evaluation time, after `permission_rules.py` returns its decision, also evaluate the DSL and apply the strictest of the two.
- `poor_cli/cli/config_cmds.py` — `poor-cli config permissions show|validate|explain <tool> <input>`.

### DSL spec

`.poor-cli/permissions.yml`:
```yaml
version: 1
defaults:
  unmatched: ask          # allow | deny | ask

rules:
  # paths
  - tool: write_file
    when:
      path_matches:
        - "src/**"
        - "tests/**"
    allow: true

  - tool: write_file
    when:
      path_matches:
        - ".github/**"
        - "infra/**"
    deny: true
    reason: "infra/CI changes require human review"

  # shell commands
  - tool: run_shell
    when:
      command_matches:
        - "^pytest(\\s|$)"
        - "^npm test"
        - "^cargo test"
    allow: true

  - tool: run_shell
    when:
      command_class: destructive          # rm -rf, dd, mkfs, force-push, drop database
    deny: true

  # provider scoping
  - tool: "*"
    when:
      provider_in: ["openai"]
      repo_label: "internal-only"
    deny: true
    reason: "internal repos must use anthropic or local providers"

  # subagent allowances
  - tool: delegate_task
    when:
      agent_name: security-reviewer
    allow: true
```

### Evaluation order
1. Existing `permission_rules.py` produces a candidate decision (allow/deny/ask).
2. DSL produces a decision over the same input.
3. Final decision = stricter of the two: deny > ask > allow.
4. If both engines say "allow" → allow.
5. Reason strings are concatenated for audit.

### Predicates supported
- `path_matches: [glob, ...]` — fnmatch on tool input path.
- `command_matches: [regex, ...]` — re.search against shell command.
- `command_class: <name>` — see `poor_cli/command_validator.py` `CommandRisk`. Reuse, don't duplicate.
- `provider_in: [name, ...]`, `model_in: [name, ...]`.
- `agent_name: <name>` — for `delegate_task`.
- `repo_label: <name>` — pulled from `.poor-cli/labels.yml` (also new; default empty).

### CLI

```
poor-cli config permissions show              # parsed rules + defaults
poor-cli config permissions validate          # exit non-zero on parse/regex errors
poor-cli config permissions explain run_shell --input "rm -rf /"
                                              # prints which rule matched and why
```

### Test plan
`tests/test_permission_dsl.py`:
- Each predicate type evaluated correctly.
- Composition with `permission_rules.py`: allow + deny → deny; ask + allow → ask; allow + allow → allow.
- Bad regex in DSL surfaces parse error, does not crash evaluation.
- `explain` returns matched-rule details.

### Commit
```
feat(permissions): declarative YAML DSL for tool/path/shell/provider scoping

Adds .poor-cli/permissions.yml with version 1 schema and predicates
(path_matches, command_matches, command_class, provider_in, model_in,
agent_name, repo_label). DSL composes with existing permission_rules
engine; final decision is the stricter of the two. Adds
`poor-cli config permissions {show,validate,explain}`.
```

### Acceptance
- Sample YAML loads and evaluates as documented.
- `permissions explain` returns the matched rule and reason.
- All existing permission tests still pass.
- Pytest green.

---

## End-of-phase checklist

- [ ] 3 commits on `main`.
- [ ] `.poor-cli/agents/*.md` loadable; `delegate_task` accepts custom agent name.
- [ ] `poor-cli task run --detach` survives shell exit.
- [ ] `.poor-cli/permissions.yml` parsed and evaluated.
- [ ] Pytest green.
