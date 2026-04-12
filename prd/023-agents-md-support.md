# PRD 023: AGENTS.md support (with CLAUDE.md fallback)

- **Wave:** 2
- **Status:** ready
- **Owner (human):** @gongahkia
- **Estimated effort:** small (3d)
- **Blocks:** —
- **Blocked by:** —
- **Files it mutates:**
  - `poor_cli/instructions.py`
  - `poor_cli/memory.py`
  - `poor_cli/auto_memory.py`
- **New files it adds:**
  - `poor_cli/agent_rules.py`
  - `tests/test_agent_rules_loader.py`

## 1. Problem

As of 2026, AGENTS.md is the Linux-Foundation-stewarded open standard across Cursor, OpenAI, Google, Sourcegraph, and Factory. CLAUDE.md is Claude Code's private format. Hand-rolled `.poor-cli/memory/` is also in use. Users rotate between tools; missing AGENTS.md isolates `poor-cli`. LEARNING.md §4.2.

## 2. Current state

`instructions.py` / `memory.py` / `auto_memory.py` locate a specific set of files. AGENTS.md is not read.

## 3. Goal & non-goals

**Goal:** at repo load, the rules layer reads (in order of precedence, highest first):

1. `AGENTS.md` in the current directory.
2. `AGENTS.md` in any ancestor directory (closest wins, hierarchical).
3. `CLAUDE.md` (for backward compat).
4. `.poor-cli/memory/*.md` entries.
5. User global `~/.poor-cli/AGENTS.md`.

Results concatenate into a single "rules" string included in context (PRD 018).

The `/memory` slash command edits **AGENTS.md by default** when writing a rule; falls back to `.poor-cli/memory/` only if AGENTS.md doesn't exist and user declines to create it.

**Non-goals:**
- Do not implement the full agents.md spec if it grows; implement current v1 (MD with optional frontmatter).
- Do not convert existing memory entries to AGENTS.md.

## 4. Design

### 4.1 Loader

```python
# poor_cli/agent_rules.py
@dataclass
class RuleSource:
    path: Path
    content: str
    precedence: int
    kind: Literal["agents_md","claude_md","poor_memory","user_global"]

def load_rules(cwd: Path) -> list[RuleSource]:
    """Returns rule sources in descending precedence."""

def merge(sources: list[RuleSource]) -> str:
    """Concatenates with separators; deduplicates identical paragraphs."""
```

### 4.2 Frontmatter

If AGENTS.md has YAML frontmatter (`---` block), honor:

```yaml
---
apply_to: ["**/*.py", "!tests/**"]   # glob patterns
priority: 10
---
```

Global sources default to `apply_to: ["**/*"]`, `priority: 0`.

### 4.3 Integration

`context_assembly.assemble()` calls `agent_rules.load_rules()` and places the merged string in `ContextSnapshot.rules`.

### 4.4 `/memory` command behavior

- If `AGENTS.md` exists in repo root: append to it.
- Else: prompt once — create AGENTS.md? If yes, create and append. If no, fall back to `.poor-cli/memory/`.

## 5. Files to create / modify / delete

**Create**
- `poor_cli/agent_rules.py`
- `tests/test_agent_rules_loader.py`

**Modify**
- `poor_cli/instructions.py` — delegate rule loading to `agent_rules`.
- `poor_cli/memory.py` — route writes through `agent_rules.append(...)`.
- `poor_cli/auto_memory.py` — same.

## 6. Implementation plan

1. Land `agent_rules.py`. Unit tests for precedence, merge, frontmatter.
2. Integrate into context assembly.
3. Update `/memory` slash-command write path.
4. Docs: note AGENTS.md is the preferred format.
5. `make lint && make test`.

## 7. Testing & acceptance criteria

- `test_agents_md_hierarchy_closest_wins`
- `test_claude_md_read_when_agents_md_absent`
- `test_frontmatter_apply_to_globs_respected`
- `test_memory_write_prefers_agents_md`

**Done criterion**
- [ ] AGENTS.md is found and merged.
- [ ] Hierarchical search works in monorepos.
- [ ] `/memory` writes to AGENTS.md by default.

## 8. Rollback / risk

Low. Purely additive.

## 9. Out-of-scope & boundary

- 🚫 Do not migrate existing CLAUDE.md content.
- 🚫 Do not implement cross-agent rules synchronization.

## 10. Related PRDs & references

- PRD 018.
- https://agents.md/
- LEARNING.md §4.2.
