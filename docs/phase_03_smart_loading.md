# Phase 3: Smart Loading & Pruning — Reduce What Gets Loaded

**Priority:** High — 🟡 Moderate solutions targeting 🔴 Critical pain points #1 and #4, plus 🟠 High #6.
**Estimated agents:** 3 (parallel)
**Dependencies:** Loosely benefits from Phase 2 (repo map helps skill routing), but not blocking.
**Philosophy:** Stop loading everything every time. The system prompt, tool schemas, and conversation history should be dynamic — load only what's relevant to the current task, prune what's no longer useful.

---

## Agent 3A: Progressive Skill/Instruction Loading

**Pain points addressed:** #4 (CLAUDE.md / system prompt bloat — 2–10K tokens per turn)
**Solution reference:** Solution #8 from SOLUTIONS.md
**Expected savings:** ~82% reduction in system prompt tokens (ClaudeFast benchmark: 15K tokens recovered)

### What to build

Break the monolithic system prompt into a skills directory loaded on-demand based on task relevance. poor-cli already has `poor_cli/instructions.py` and `poor_cli/skills.py` — enhance these to implement progressive disclosure.

### Implementation details

1. **Audit current instruction loading** — read `poor_cli/instructions.py` thoroughly:
   - What instructions are loaded on every request?
   - How large is the total instruction payload?
   - Is there any conditional loading?

2. **Design skill taxonomy** — break instructions into discrete skills:
   ```
   skills/
     core.md          — always loaded (safety, basic behavior, 500 tokens)
     git.md           — loaded when task involves git operations
     testing.md       — loaded when task involves test generation/running
     refactoring.md   — loaded when task involves code changes
     debugging.md     — loaded when task involves error analysis
     deployment.md    — loaded when task involves deploy/CI
     review.md        — loaded when task involves code review
     multiplayer.md   — loaded when multiplayer session is active
     economy.md       — loaded when economy mode is active
   ```

3. **Task classifier** — build a lightweight classifier that maps the current user prompt to required skills:
   ```python
   def classify_required_skills(prompt: str, context: SessionContext) -> list[str]:
       skills = ["core"]  # always loaded
       # keyword-based first pass
       if any(w in prompt.lower() for w in ["git", "commit", "push", "branch", "merge"]):
           skills.append("git")
       if any(w in prompt.lower() for w in ["test", "spec", "assert", "coverage"]):
           skills.append("testing")
       # context-based: if multiplayer active, load multiplayer skill
       if context.multiplayer_active:
           skills.append("multiplayer")
       # ... etc
       return skills
   ```

4. **Skill registry** — maintain a registry mapping skill names to instruction content:
   ```python
   class SkillRegistry:
       def __init__(self, skills_dir: Path):
           self.skills = {}
           for md in skills_dir.glob("*.md"):
               self.skills[md.stem] = md.read_text()
       
       def load(self, skill_names: list[str]) -> str:
           return "\n\n".join(self.skills[s] for s in skill_names if s in self.skills)
   ```

5. **Integration with prompt construction** — replace the monolithic system prompt injection with dynamic skill loading. In the prompt assembly pipeline:
   ```python
   required_skills = classify_required_skills(user_prompt, session)
   skill_instructions = skill_registry.load(required_skills)
   system_prompt = BASE_SYSTEM_PROMPT + "\n\n" + skill_instructions
   ```

6. **User-defined skills** — support user skills in `.poor-cli/skills/` that follow the same pattern, loaded alongside built-in skills.

7. **Skill loading visibility** — show which skills are loaded via `/instructions` command or in the lualine status.

### Files to create/modify
- `poor_cli/instructions.py` (primary — refactor to use skill registry)
- `poor_cli/skills.py` (enhance with registry pattern)
- `poor_cli/skills/` directory (new — break out instruction content into files)
- Prompt assembly logic in core engine

### Acceptance criteria
- [ ] Instructions broken into ≥8 discrete skill files
- [ ] Core skill always loaded, others loaded on-demand
- [ ] Keyword-based task classifier routes prompts to skills
- [ ] System prompt size measurably reduced for non-complex tasks
- [ ] `/instructions` shows which skills are currently loaded
- [ ] User skills in `.poor-cli/skills/` loaded when relevant
- [ ] Test: "fix typo in README" loads only core skill (~500 tokens vs full ~5000)

### References
- [Anthropic Skills](https://docs.claude.com/en/docs/agents-and-tools/agent-skills/overview)
- ClaudeFast Code Kit progressive disclosure pattern

---

## Agent 3B: Lazy Tool Schema Loading

**Pain points addressed:** #6 (verbose tool schemas — 8–15K tokens per session)
**Solution reference:** Solution #14 from SOLUTIONS.md
**Expected savings:** 50-80% reduction in tool schema tokens per request

### What to build

Instead of injecting all tool schemas into every request, dynamically load only the schemas needed for the current task. This is a **greenfield gap** — no standard implementation exists.

### Implementation details

1. **Audit current tool loading** — find where tool schemas are injected into requests:
   - How many tools are defined?
   - How large is the total schema payload?
   - Are all tools sent every turn?

2. **Tool classification** — categorize tools by usage domain:
   ```python
   TOOL_GROUPS = {
       "core": ["read_file", "write_file", "edit_file", "bash", "list_directory"],
       "search": ["glob_files", "grep_files"],
       "git": ["git_status", "git_diff", "git_status_diff", "apply_patch_unified"],
       "github": ["gh_pr_list", "gh_pr_view", "gh_pr_create", "gh_pr_comment",
                   "gh_issue_list", "gh_issue_view"],
       "quality": ["run_tests", "format_and_lint", "dependency_inspect", "process_logs"],
       "network": ["fetch_url", "web_search"],
       "file_ops": ["copy_file", "move_file", "delete_file", "create_directory", "diff_files"],
       "data": ["json_yaml_edit"],
   }
   ```

3. **Task-to-tools classifier** — map the current task to required tool groups:
   ```python
   def required_tool_groups(prompt: str, context: SessionContext) -> list[str]:
       groups = ["core"]  # always available
       if any(w in prompt.lower() for w in ["search", "find", "grep", "where"]):
           groups.append("search")
       if any(w in prompt.lower() for w in ["git", "commit", "diff", "branch"]):
           groups.append("git")
       if any(w in prompt.lower() for w in ["pr", "issue", "github"]):
           groups.append("github")
       # ... etc
       return groups
   ```

4. **On-demand schema injection** — modify the prompt construction to only include schemas for required tool groups. If the model requests a tool not in the current set, dynamically add that tool group and retry.

5. **MCP server lazy loading** — for MCP servers, defer schema loading until the server's tools are actually needed:
   ```python
   class LazyMCPServer:
       def __init__(self, config):
           self._schema = None  # loaded on first use
       
       async def get_schema(self):
           if self._schema is None:
               self._schema = await self._load_schema()
           return self._schema
   ```

6. **Fallback** — if the model asks for a tool not in the loaded set, add it dynamically and inform the model. Never silently fail.

### Files to create/modify
- `poor_cli/command_manifest.py` (add tool group classification)
- `poor_cli/enhanced_tools.py` (lazy schema loading logic)
- `poor_cli/mcp_scaffold.py` (lazy MCP schema loading)
- Prompt assembly logic (only inject selected tool schemas)

### Acceptance criteria
- [ ] Tools classified into groups by domain
- [ ] Only relevant tool groups loaded per request
- [ ] MCP server schemas loaded lazily on first use
- [ ] Missing tool triggers dynamic loading + retry (no silent failure)
- [ ] Measured: total tool schema tokens reduced by 50%+ for typical tasks
- [ ] Test: "explain this function" only loads core + search tools

### References
- No standard implementation exists — this is greenfield
- Closest analog: dynamic MCP server selection in agent frameworks

---

## Agent 3C: Importance-Weighted History Pruning

**Pain points addressed:** #1 (context window accumulation — O(n²) growth)
**Solution reference:** Solution #12 from SOLUTIONS.md
**Expected savings:** 30-50% context reduction without quality loss

### What to build

Instead of blanket summarization (what `/compact` does), score each conversation turn for importance and selectively prune the lowest-value turns. This is smarter than compaction — it preserves high-value context while dropping noise.

### Implementation details

1. **Turn importance scoring** — score each turn on multiple axes:
   ```python
   def score_turn(turn: ConversationTurn, current_context: SessionContext) -> float:
       score = 0.0
       # recency: recent turns matter more
       score += recency_score(turn.timestamp, current_context.current_time)
       # tool results: successful tool calls > failed tool calls
       if turn.has_tool_result:
           score += 0.3 if turn.tool_succeeded else -0.2
       # file relevance: turns about currently-open files matter more
       if turn.references_active_files(current_context.active_files):
           score += 0.4
       # user messages always score higher than assistant messages
       if turn.role == "user":
           score += 0.3
       # planning/decision turns matter more than exploration turns
       if turn.contains_decision or turn.contains_plan:
           score += 0.5
       # failed attempts that were superseded: low value
       if turn.was_superseded:
           score -= 0.5
       return score
   ```

2. **Pruning strategy** — when context exceeds threshold:
   - Score all turns
   - Sort by score ascending
   - Remove lowest-scored turns until context is under target
   - Never remove: current turn, last user message, pinned context
   - For removed turns, optionally keep a one-line summary

3. **Integration with auto-compaction** — this works alongside Phase 1's auto-compaction:
   - Phase 1 compaction = blanket summary (fast, lossy)
   - Phase 3 pruning = selective removal (slower, preserves more)
   - Pipeline: first prune low-value turns, then compact remaining if still over budget

4. **Supersession detection** — mark turns as "superseded" when:
   - A failed tool call was retried successfully
   - The user corrected a previous instruction
   - A file was read, then re-read after edits (old read is stale)

5. **Pruning visibility** — show the user what was pruned and why:
   ```
   [auto-pruned] 3 turns removed (2 failed tool calls, 1 stale file read)
   ```

### Files to create/modify
- `poor_cli/history_pruning.py` (new, ~250 lines — scoring + pruning logic)
- `poor_cli/context_optimizer.py` (integrate pruning into compaction pipeline)
- `poor_cli/history.py` (add scoring metadata to conversation turns)

### Acceptance criteria
- [ ] Turn importance scoring implemented with recency, relevance, success axes
- [ ] Selective pruning removes lowest-value turns first
- [ ] Failed-then-retried tool calls marked as superseded and pruned first
- [ ] User messages and current context never pruned
- [ ] Pruning integrates with auto-compaction pipeline
- [ ] User notified of pruning actions
- [ ] Test: simulate conversation with 5 failed tool calls + 5 successful, verify failed ones pruned first

### References
- [H2O paper (NeurIPS 2023)](https://arxiv.org/abs/2306.14048) — heavy hitter oracle for KV cache
- [Scissorhands](https://arxiv.org/abs/2305.17118) — persistence of importance hypothesis
- [Letta/MemGPT](https://github.com/letta-ai/letta) — memory hierarchy implementation
