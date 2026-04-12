# PRD 014: Diff Review panel with hunk-level accept / reject

- **Wave:** 1
- **Status:** ready
- **Owner (human):** @gongahkia
- **Estimated effort:** x-large (2+ weeks)
- **Blocks:** 051
- **Blocked by:** — (stands on its own; benefits from PRD 017 being done but does not require it)
- **Files it mutates:**
  - `poor_cli/server/runtime.py` (narrow — adds 2 RPC methods only)
  - `poor_cli/checkpoint.py` (narrow — accept integration)
  - `poor_cli/tools_async.py` (narrow — stage edits in "review" mode)
  - `nvim-poor-cli/lua/poor-cli/init.lua` (small — register the new module)
  - `nvim-poor-cli/lua/poor-cli/keymaps.lua` (add mappings)
  - `nvim-poor-cli/lua/poor-cli/commands.lua` (add `:PoorCliReview` command)
  - `nvim-poor-cli/lua/poor-cli/config.lua` (new options)
- **New files it adds:**
  - `nvim-poor-cli/lua/poor-cli/diff_review.lua` (main module)
  - `nvim-poor-cli/lua/poor-cli/diff_parser.lua` (unified-diff parsing)
  - `nvim-poor-cli/tests/diff_review_spec.lua` (plenary.busted)
  - `poor_cli/edit_staging.py` (server-side staging of pending edits)
  - `tests/test_edit_staging.py`

---

## 1. Problem

When the agent edits a file, there is no visible review step. The edit lands; the user discovers it via checkpoint rollback or a broken build. This is the single biggest UX gap identified in [`LEARNING.md` §3.1](../LEARNING.md). The 2026 market has moved to hunk-level accept/reject:

- Avante.nvim: select, describe, sidebar diff, accept/reject.
- Cursor Composer / Windsurf Cascade: agent plans, shows diff, hunk-by-hunk apply.
- claude-preview.nvim: live diff preview for Claude Code's file edits.

PRD delivers a first-class **Diff Review panel** with hunk-level keymaps (`ga`/`gr`/`gA`/`gR`/`gn`/`gp`/`gc`), integrated with the existing checkpoint system.

## 2. Current state

Current flow:
1. Agent calls `write_file`/`edit_file`/`apply_patch_unified` in `tools_async.py`.
2. A checkpoint is created before the write (via `checkpoint.py`).
3. The write applies immediately.
4. User sees the diff only if they look at `/diff` or realize something is off.

Relevant files:

- `poor_cli/tools_async.py` — tool implementations for writes/edits.
- `poor_cli/checkpoint.py` — creates pre-mutation snapshots.
- `poor_cli/server/runtime.py` — RPC dispatch.
- `nvim-poor-cli/lua/poor-cli/chat.lua` — where the agent's prose about edits lands.
- `nvim-poor-cli/lua/poor-cli/panel_base.lua` — shared panel abstraction.

## 3. Goal & non-goals

**Goal:** when the agent proposes a file edit, the edit is **staged** (not applied) and surfaced in a Diff Review panel. The user can accept or reject each hunk individually, regenerate a single hunk with an instruction, or accept/reject all. Applying accepted hunks creates one named checkpoint per batch, with the triggering prompt as the label. A config switch keeps the old "auto-apply" behavior for users who prefer it.

**Non-goals:**
- Do not replace the checkpoint system (this PRD integrates with it).
- Do not implement full three-way merge (single-source diff is fine — agent vs current).
- Do not ship automatic conflict resolution.
- Do not ship syntax-highlighted rich diff rendering beyond what Neovim's built-in `:diffthis` / treesitter give us.

## 4. Design

### 4.1 Two modes

Config option `diff_review.mode`:

- `auto` — existing behavior, edits apply immediately. (Migration path; default for first release of this PRD → `review`.)
- `review` — edits stage into a review queue; panel opens; nothing lands until accepted.
- `review_risky` — only mutations that cross heuristic thresholds (>N lines, >M files, high-risk paths like `main.py`, `package.json`) go to review; small edits auto-apply.

> **DECISION REQUIRED:** which mode is default on first ship. Recommendation: `review` — users explicitly opt into auto-apply.

### 4.2 Data flow

```
     Agent decides to edit
              │
              ▼
      tools_async.edit_file(...)
              │
              ├── if mode == "auto":        apply + checkpoint (existing)
              │
              └── if mode == "review":
                     │
                     ▼
            edit_staging.stage(edit)    ← new
                     │
                     ▼
            RPC event: previewEdits    ← Lua listens
                     │
                     ▼
          diff_review.open_review()     (Lua)
                     │
           ┌─────────┴──────────┐
           ▼                    ▼
     user accepts hunk    user rejects hunk
           │                    │
           ▼                    ▼
     RPC: applyHunk       RPC: rejectHunk
           │                    │
           └─────┬──────────────┘
                 ▼
        on last hunk: checkpoint
```

### 4.3 Server-side: `edit_staging.py`

```python
# poor_cli/edit_staging.py
from dataclasses import dataclass, field
from uuid import uuid4
from pathlib import Path

@dataclass(frozen=True)
class Hunk:
    hunk_id: str          # stable id
    path: str             # relative path
    header: str           # "@@ -L,N +L,M @@"
    before: list[str]
    after: list[str]
    line_start: int       # 1-indexed

@dataclass
class PendingEdit:
    edit_id: str
    path: str
    original: bytes       # full original file content (for undo)
    proposed: bytes       # full proposed file content
    hunks: list[Hunk]
    tool_call_id: str     # links back to the agent turn
    prompt: str           # the user prompt that triggered this

class EditStage:
    """Holds pending edits until accepted or rejected."""
    def stage(self, path: Path, proposed_content: bytes, *, tool_call_id: str, prompt: str) -> PendingEdit: ...
    def list_pending(self) -> list[PendingEdit]: ...
    def accept_hunk(self, edit_id: str, hunk_id: str) -> PendingEdit: ...
    def reject_hunk(self, edit_id: str, hunk_id: str) -> PendingEdit: ...
    def accept_all(self, edit_id: str) -> None: ...
    def reject_all(self, edit_id: str) -> None: ...
    def regenerate_hunk(self, edit_id: str, hunk_id: str, *, instruction: str) -> Hunk: ...
    def finalize(self, edit_id: str) -> Path | None:
        """Applies all accepted hunks. Creates a single checkpoint. Returns path written."""
```

Hunks are computed via `difflib.unified_diff` on the original vs proposed bytes.

### 4.4 RPC surface (added to `runtime.py`)

| Method | Params | Returns |
|---|---|---|
| `poor-cli/listPendingEdits` | — | `{edits: PendingEdit[]}` |
| `poor-cli/previewEdit` | `{editId}` | `{edit: PendingEdit, diffText: string}` |
| `poor-cli/acceptHunk` | `{editId, hunkId}` | `{edit}` |
| `poor-cli/rejectHunk` | `{editId, hunkId}` | `{edit}` |
| `poor-cli/acceptAll` | `{editId}` | `{checkpointId}` |
| `poor-cli/rejectAll` | `{editId}` | `{}` |
| `poor-cli/regenerateHunk` | `{editId, hunkId, instruction}` | `{hunk}` |
| `poor-cli/stageEvent` | (notification push) | `{edit}` |

### 4.5 Neovim side: `diff_review.lua`

Panel layout:

```
┌──────────────────────────────────────────────────────────────┐
│  [1/3] foo/bar.py   (2 hunks)                                │
│  Prompt: "add error handling to parse()"                     │
│  Status: pending                                             │
├──────────────────────────────────────────────────────────────┤
│  ga accept hunk   gr reject hunk   gc regenerate hunk        │
│  gA accept all    gR reject all    gn next   gp prev   q close │
├──────────────────────────────────────────────────────────────┤
│  @@ -10,3 +10,8 @@  def parse(s):                            │
│  -    return json.loads(s)                                   │
│  +    try:                                                   │
│  +        return json.loads(s)                               │
│  +    except json.JSONDecodeError as e:                      │
│  +        raise ParseError(f"bad JSON: {e}") from e          │
│  [pending]                                                   │
├──────────────────────────────────────────────────────────────┤
│  @@ -20,1 +25,4 @@  def main():                              │
│  ...                                                         │
│  [accepted]                                                  │
└──────────────────────────────────────────────────────────────┘
```

Alternative view toggled by `\d`: side-by-side split using `:diffthis` on two scratch buffers (original vs proposed) — leverages Neovim's built-in diff rendering.

### 4.6 Keymaps (inside the panel; all `noremap` buffer-local)

| Key | Action |
|---|---|
| `ga` | Accept hunk under cursor |
| `gr` | Reject hunk under cursor |
| `gA` | Accept all remaining hunks in this edit |
| `gR` | Reject all remaining hunks in this edit |
| `gn` | Next hunk (jump) |
| `gp` | Previous hunk |
| `gc` | Regenerate hunk under cursor (prompts for optional instruction) |
| `gl` | Cycle layout: unified ↔ side-by-side |
| `gf` | Jump to the file at that line in the original buffer |
| `]e` | Next pending edit |
| `[e` | Previous pending edit |
| `q` | Close panel (edits remain pending) |

### 4.7 Checkpoint integration

When `acceptAll` or the last-hunk acceptance fires `finalize`:

1. Write all accepted hunks to the file.
2. Create a named checkpoint via `checkpoint.py`: label = truncated user prompt + edit count.
3. Emit `poor-cli/editCommitted` event.

Rejecting all hunks discards the pending edit with no checkpoint.

### 4.8 Config options

```lua
-- nvim-poor-cli/lua/poor-cli/config.lua
diff_review = {
    mode = "review",          -- "auto" | "review" | "review_risky"
    layout = "unified",       -- "unified" | "side_by_side"
    panel_position = "right",
    panel_width = 90,
    auto_open = true,         -- pop panel on staged edit
    risky_paths = {"package.json", "pyproject.toml", "Cargo.toml", "/main\\.", "/__init__\\."},
    risky_line_threshold = 50,
}
```

### 4.9 Auto-apply fallback

A hard requirement: users running automations (cron, scheduled) cannot be blocked by an interactive panel. When the caller is non-interactive (detected via the session flag), staging is bypassed and the edit auto-applies with a note in the audit log.

## 5. Files to create / modify / delete

**Create (server)**
- `poor_cli/edit_staging.py` — `PendingEdit`, `Hunk`, `EditStage` as spec'd.
- `tests/test_edit_staging.py` — unit tests for staging + hunk computation + finalize.

**Create (Neovim)**
- `nvim-poor-cli/lua/poor-cli/diff_review.lua` — module: open/close panel, render, hunk navigation, keymaps.
- `nvim-poor-cli/lua/poor-cli/diff_parser.lua` — parse unified-diff text into hunks with line ranges.
- `nvim-poor-cli/tests/diff_review_spec.lua` — plenary.busted tests.

**Modify (server, narrow)**
- `poor_cli/tools_async.py` — at every edit tool (`write_file`, `edit_file`, `apply_patch_unified`), branch on `diff_review.mode`. If `review`, call `edit_staging.stage(...)` instead of writing immediately.
- `poor_cli/checkpoint.py` — helper: `create_for_batch(edit_id, path, label)`.
- `poor_cli/server/runtime.py` — register the new RPC methods. 🟠 Touch only the dispatch table; no broader refactor.

**Modify (Neovim, narrow)**
- `lua/poor-cli/init.lua` — add `diff_review` to `EAGER_SETUPS`.
- `lua/poor-cli/keymaps.lua` — global `<leader>pv` to toggle the review panel.
- `lua/poor-cli/commands.lua` — `:PoorCliReview`, `:PoorCliReviewClose`, `:PoorCliDiffLayout`.
- `lua/poor-cli/config.lua` — defaults for `diff_review`.

## 6. Implementation plan

### Phase A — server staging (can land before any Lua)

1. Implement `PendingEdit`, `Hunk`, `EditStage` in `edit_staging.py`. Use `difflib.unified_diff` for hunk computation.
2. Add an in-memory store for pending edits keyed by `edit_id`. Persist nothing on disk for v1 (edits are tied to the running session).
3. Wire `tools_async.edit_file` / `write_file` / `apply_patch_unified` to branch on the mode config. In `review` mode, return an `EditOutcome` with `{status: "pending_review", edit_id}`.
4. Add RPC methods in `runtime.py`. Emit `poor-cli/stageEvent` on stage. Emit `poor-cli/editCommitted` on finalize.
5. Write `tests/test_edit_staging.py`: stage → list → accept hunk → finalize → verify file contents + checkpoint exists. Also: rejectAll → verify file unchanged + no checkpoint.

### Phase B — Neovim diff panel (Lua)

6. `diff_parser.lua`: function `parse(diff_text) -> { hunks: [{hunk_id, header, before, after, line_start}] }`. Unit-test.
7. `diff_review.lua`:
   - `M.open()` / `M.close()` — manage a right split buffer and an optional side-by-side set.
   - `M.render(pending_edits)` — renders the panel using extmarks for `[accepted]`/`[rejected]`/`[pending]` tags.
   - Keymaps bound buffer-local in `M.open`.
   - RPC listeners for `stageEvent` (auto-open) and `editCommitted` (refresh).
8. Hook into `init.lua` for setup; register commands and keymaps.
9. Plenary tests (see PRD 065 for plenary infrastructure — if that hasn't landed, this PRD depends on it).

### Phase C — polish

10. Layout switcher (`gl`) between unified and side-by-side (`:diffthis` buffers).
11. `gc` hunk regenerate: prompt for optional instruction, RPC → `regenerateHunk`, swap the hunk.
12. Auto-open config, non-interactive bypass, audit-log event on mode switch.
13. Docs: update plugin README with the new keymaps and modes.

## 7. Testing & acceptance criteria

**Server tests (`tests/test_edit_staging.py`)**
- `test_stage_computes_hunks_from_bytes`
- `test_accept_hunk_marks_accepted_without_writing_file`
- `test_reject_hunk_leaves_file_unchanged_after_finalize`
- `test_accept_all_writes_file_and_creates_checkpoint`
- `test_reject_all_never_writes_file`
- `test_regenerate_hunk_swaps_in_new_content`
- `test_non_interactive_bypass_applies_immediately`
- `test_audit_log_records_stage_and_finalize`

**Lua tests (`nvim-poor-cli/tests/diff_review_spec.lua`)**
- `parses a simple unified diff into one hunk`
- `opens panel on stage event`
- `ga on a hunk marks it accepted and refreshes`
- `gR on an edit discards it`
- `gl toggles layout between unified and side_by_side`

**Manual verification**
- `GEMINI_API_KEY=... poor-cli exec --prompt "add a docstring to poor_cli/utils.py"` in `review` mode → panel pops, hunk visible, `ga` accepts, `:checkhealth poor-cli` still green.
- Same flow in `auto` mode → edit applies directly, no panel.

**Commands to pass**
- `make lint && make test`
- `:PlenaryBustedDirectory nvim-poor-cli/tests/` (requires PRD 065)

**Done criterion**
- [ ] `diff_review.mode = "review"` default on first release (pending owner decision 4.1).
- [ ] Hunk-level accept/reject works end-to-end.
- [ ] Checkpoints labeled with the user prompt.
- [ ] Panel auto-opens on stage.
- [ ] All tests pass.

## 8. Rollback / risk

Medium. This changes the edit flow — if the panel is broken users cannot apply edits. Mitigations:

- Default-off escape hatch: `POOR_CLI_DIFF_REVIEW=auto` env var overrides config to fall back.
- All edits still go through checkpoints, so even if the panel misbehaves there is no data loss.
- Non-interactive callers bypass staging entirely.

No persistence changes. Pending edits live in memory; a crash drops them (and the pre-stage checkpoint in existing code ensures no data loss).

## 9. Out-of-scope & boundary

- 🚫 Do not rewrite `tools_async.py` beyond the branch in the write/edit tools.
- 🚫 Do not rewrite `checkpoint.py` semantics; only add the batch-label helper.
- 🚫 Do not touch `chat.lua` beyond wiring an optional notification that a review is pending (see PRD 015 for real streaming UX).
- 🚫 Do not implement three-way merge.
- 🚫 Do not persist pending edits across server restarts (v2 work).

## 10. Related PRDs & references

- PRD 051 (gitsigns bridge — depends on this).
- PRD 065 (Lua testing infra — helpful prerequisite).
- LEARNING.md §3.1 "The single most-needed feature: a diff-review UX."
- claude-preview.nvim: https://github.com/Cannon07/claude-preview.nvim
- avante.nvim: https://github.com/yetone/avante.nvim
- Aider edit-format docs: https://aider.chat/docs/
