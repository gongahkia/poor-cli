# Phase 1: Quick Wins — Drop-in Integrations

**Priority:** Highest — these are 🟢 Easy solutions targeting 🔴 Critical and 🟠 High pain points.
**Estimated agents:** 4 (parallel)
**Dependencies:** None — all independent, no cross-agent blocking.
**Philosophy:** Ship maximum token savings with minimum code changes. Every solution here is either a drop-in binary, a config tweak, or a thin wrapper around existing infrastructure. No new architectures.

---

## Agent 1A: RTK CLI Output Proxy Integration

**Pain points addressed:** #9 (ambient noise pollution), #2 (tool output bloat, shell-mediated), #3 (codebase reading inefficiency for shell paths)
**Solution reference:** Solution #23 from SOLUTIONS.md
**Expected savings:** 60–90% on shell command output tokens

### What to build

Integrate [RTK (Rust Token Killer)](https://github.com/rtk-ai/rtk) as a pre-execution middleware in poor-cli's tool execution layer. RTK intercepts shell commands and rewrites their output into token-compact form before it reaches the agent's context.

### Implementation details

1. **Add RTK detection** in `poor-cli/utils.py` or a new `poor-cli/rtk_integration.py`:
   - Check if `rtk` binary is on PATH via `shutil.which("rtk")`
   - Expose a config flag `use_rtk: bool = True` in the config system
   - If rtk not found and `use_rtk` is True, log a warning suggesting `brew install rtk`

2. **Wrap tool execution** — the primary integration point is wherever poor-cli spawns shell subprocesses for tool calls. Key files:
   - `poor-cli/enhanced_tools.py` — the `bash` tool implementation
   - Any subprocess call that runs user-facing shell commands (git, npm, cargo, etc.)
   
   For each supported command, prefix with `rtk` before spawning:
   ```python
   # before
   result = await asyncio.create_subprocess_shell(cmd, ...)
   # after
   if self.rtk_available and self._is_rtk_supported(cmd):
       cmd = f"rtk {cmd}"
   result = await asyncio.create_subprocess_shell(cmd, ...)
   ```

3. **RTK supported command detection** — maintain a set of command prefixes that RTK handles:
   ```python
   RTK_COMMANDS = {"git", "gh", "cargo", "npm", "pnpm", "yarn", "pytest", "ruff",
                   "docker", "kubectl", "aws", "curl", "ls", "cat", "grep", "find",
                   "eslint", "prettier", "tsc", "go", "make", "cmake"}
   ```

4. **Tee mode for failures** — when a tool call fails (non-zero exit), re-run without RTK to get full output for debugging. RTK has a native tee mode (`rtk --tee`) that persists raw output; prefer that.

5. **Config integration** — add to `poor-cli/repo_config.py` or equivalent:
   ```yaml
   token_optimization:
     rtk_enabled: true
     rtk_tee_on_failure: true
   ```

6. **Neovim plugin awareness** — in `nvim-poor-cli/lua/poor-cli/config.lua`, add an `rtk_enabled` field so users can toggle from Neovim config.

### Files to create/modify
- `poor-cli/rtk_integration.py` (new, ~80 lines)
- `poor-cli/enhanced_tools.py` (modify bash tool to use RTK wrapper)
- `poor-cli/repo_config.py` (add rtk config fields)
- `nvim-poor-cli/lua/poor-cli/config.lua` (add rtk_enabled default)

### Acceptance criteria
- [ ] `rtk` presence auto-detected on startup
- [ ] Shell tool calls for supported commands are transparently prefixed with `rtk`
- [ ] Failed commands fall back to raw output (tee mode)
- [ ] Config flag disables RTK entirely
- [ ] No behavioral change when RTK is not installed
- [ ] Unit test: mock subprocess, verify rtk prefix applied/not applied

### References
- [RTK GitHub](https://github.com/rtk-ai/rtk)
- [RTK architecture](https://github.com/rtk-ai/rtk/blob/master/docs/contributing/ARCHITECTURE.md)

---

## Agent 1B: Enhanced Diff-Based Editing

**Pain points addressed:** #10 (edit format tax — up to 3× token waste per edit)
**Solution reference:** Solution #2 from SOLUTIONS.md
**Expected savings:** ~31% token reduction on file edits (EASE paper benchmark)

### What to build

Audit and enhance poor-cli's existing `edit_formats.py` to ensure the most token-efficient edit format is used by default, and add support for unified diff and search/replace block formats.

### Implementation details

1. **Audit current implementation** — read `poor-cli/edit_formats.py` thoroughly. Determine:
   - What edit format is currently used (full rewrite? search/replace? unified diff?)
   - Whether the format is provider-agnostic or provider-specific
   - Whether fallback to full-file rewrite happens silently

2. **Implement search/replace block format** (if not present):
   ```
   <<<<<<< SEARCH
   old code here
   =======
   new code here
   >>>>>>> REPLACE
   ```
   This is Aider's proven format — minimal tokens, high reliability.

3. **Implement unified diff format** as an alternative:
   ```diff
   --- a/file.py
   +++ b/file.py
   @@ -10,3 +10,4 @@
    existing line
   -old line
   +new line
   +added line
   ```

4. **Format selection heuristic** — choose format based on edit size:
   - < 5 lines changed → search/replace blocks (most compact)
   - 5–50 lines changed → unified diff
   - > 50 lines or new file → full file write (unavoidable)

5. **Provider-specific tuning** — some models handle certain formats better:
   - Claude/Anthropic: search/replace blocks work well
   - GPT models: unified diff or `apply_patch` format
   - Gemini: search/replace blocks
   - Add format preference to provider config

6. **Validation** — after applying an edit, verify the resulting file is syntactically valid (use tree-sitter if available, or at minimum check for balanced braces/brackets).

### Files to create/modify
- `poor-cli/edit_formats.py` (primary — enhance/rewrite)
- `poor-cli/providers/base.py` (add `preferred_edit_format` to provider interface)
- Provider implementations as needed for format preferences

### Acceptance criteria
- [ ] Search/replace block format implemented and working
- [ ] Unified diff format implemented and working
- [ ] Format auto-selected based on edit size heuristic
- [ ] Provider-specific format preferences respected
- [ ] No silent fallback to full-file rewrite without logging
- [ ] Test: same edit produces fewer tokens via diff vs full rewrite

### References
- [Aider edit formats](https://aider.chat/docs/more/edit-formats.html)
- [EASE paper](https://arxiv.org/abs/2407.04816)
- OpenAI `apply_patch` format

---

## Agent 1C: Enhanced Context Compaction

**Pain points addressed:** #1 (context window accumulation — the #1 cost driver)
**Solution reference:** Solution #5 from SOLUTIONS.md
**Expected savings:** Prevents O(n²) token growth in long sessions

### What to build

Enhance poor-cli's existing `/compact` command and `context_optimizer.py` to be smarter about what gets compacted, when auto-compaction triggers, and what gets preserved.

### Implementation details

1. **Audit current implementation** — read `poor-cli/context_optimizer.py` and `poor-cli/context_contract.py`. Understand:
   - Current compaction strategy (blanket summary? selective?)
   - Token counting mechanism
   - Trigger threshold (manual only? auto?)

2. **Implement tiered compaction** — not all context is equal:
   - **Tier 1 (always preserve):** Current user message, last assistant response, active file contents, pinned context
   - **Tier 2 (summarize):** Older conversation turns, completed tool call results
   - **Tier 3 (drop):** Failed tool attempts (keep only the lesson), raw shell output already processed, intermediate reasoning

3. **Auto-compaction trigger** — add a configurable threshold:
   ```python
   auto_compact_threshold: float = 0.7  # compact when context hits 70% of window
   auto_compact_target: float = 0.4     # compact down to 40% of window
   ```
   After each turn, check total context size. If above threshold, auto-compact Tier 3 first, then Tier 2.

4. **Compaction summary quality** — when summarizing older turns, use the current (cheaper) model to produce a structured summary:
   ```
   ## Session Summary (turns 1-15)
   - User asked to refactor auth middleware
   - Files modified: auth.py, middleware.py, tests/test_auth.py
   - Key decisions: chose JWT over session tokens, added rate limiting
   - Unresolved: test for edge case with expired tokens
   ```

5. **Integration with economy mode** — when in `/broke` (frugal) mode, compact more aggressively. In `/my-treat` (quality) mode, preserve more context.

6. **Neovim feedback** — show compaction events in lualine or as notifications so the user knows context was compacted.

### Files to create/modify
- `poor-cli/context_optimizer.py` (primary — enhance compaction logic)
- `poor-cli/context_contract.py` (add tier classification)
- `poor-cli/context_providers.py` (integrate auto-compaction check)
- `nvim-poor-cli/lua/poor-cli/lualine.lua` (show compaction status)

### Acceptance criteria
- [ ] Tiered compaction implemented (preserve/summarize/drop)
- [ ] Auto-compaction triggers at configurable threshold
- [ ] Economy mode influences compaction aggressiveness
- [ ] Compaction produces structured summaries, not lossy truncation
- [ ] `/compact` manual command enhanced with tier options (`/compact aggressive`, `/compact gentle`)
- [ ] User notified when auto-compaction occurs
- [ ] Test: simulate 50-turn conversation, verify compaction keeps context under target

### References
- [Claude Code `/compact`](https://docs.claude.com/en/docs/agents-and-tools/claude-code/overview)
- GPT-5.2-Codex context compaction approach

---

## Agent 1D: Terse Output Mode (Caveman-Style)

**Pain points addressed:** #18 (markdown formatting overhead), #14 (CoT verbosity, partial)
**Solution reference:** Solution #24 from SOLUTIONS.md
**Expected savings:** ~75% output token reduction (bounded to 5-15% of total session cost)

### What to build

Add a built-in terse output mode to poor-cli that instructs the model to strip prose filler, articles, pleasantries, and verbose formatting. This is the lowest-impact solution but also the lowest-effort — implement it as part of the economy system that already exists (`/broke` mode).

### Implementation details

1. **Extend `/broke` mode** — poor-cli already has `/broke` (terse) and `/my-treat` (comprehensive) modes. The `/broke` mode should include a system prompt directive for compressed output.

2. **Add terse output directive** to the system prompt when in frugal/broke mode:
   ```
   OUTPUT RULES (frugal mode active):
   - No articles (a/an/the) in explanations
   - No pleasantries, hedging, or filler
   - No markdown headers for short responses
   - Preserve: code blocks, technical terms, error messages, git prose
   - Target: minimum tokens for maximum information density
   ```

3. **Integration point** — find where poor-cli constructs the system prompt (likely in the core engine or provider layer) and inject the terse directive when economy mode is `frugal` or `broke`.

4. **Graduated verbosity** — tie output verbosity to the existing economy presets:
   - `frugal` → maximum compression (caveman-style)
   - `balanced` → normal output
   - `quality` → comprehensive explanations allowed

5. **Preserve critical prose** — git commit messages, PR descriptions, user-facing docs should always use proper grammar regardless of mode.

### Files to create/modify
- `poor-cli/profiles.py` or wherever economy/output mode directives live
- System prompt construction logic (in core engine)
- No Neovim changes needed — economy mode already exposed via commands

### Acceptance criteria
- [ ] `/broke` mode adds terse output directive to system prompt
- [ ] Output measurably shorter in frugal mode (spot-check 5 prompts)
- [ ] Code blocks, error messages, git prose unaffected
- [ ] Economy presets map to output verbosity levels
- [ ] No changes to `/my-treat` or `balanced` modes

### References
- [Caveman skill](https://github.com/JuliusBrussee/caveman)
