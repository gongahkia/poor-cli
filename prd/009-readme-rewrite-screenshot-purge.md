# PRD 009: Rewrite README for Neovim-only era; purge stale TUI screenshots

- **Wave:** 1
- **Status:** ready
- **Owner (human):** @gongahkia
- **Estimated effort:** small (1d)
- **Blocks:** —
- **Blocked by:** —
- **Files it mutates:**
  - `README.md`
  - `nvim-poor-cli/README.md` (alignment pass only)
  - `asset/reference/v5/*.png` (delete or replace)
- **New files it adds:**
  - `asset/reference/v6/*.png` (new screenshots — owner provides or recorder does)
  - `asset/demo.gif` (optional; LONGTERM-TODO C2)

## 1. Problem

The project consolidated to Neovim-only. README still shows TUI screenshots (`asset/reference/v5/*.png`), installs instructions for `./run_tui.sh`, and references retired clients. New users hit a confusing front door. LONGTERM-TODO L6 flags the rewrite; LEARNING.md §1.1 confirms the consolidation.

Also: no demo GIF (LONGTERM-TODO C2 — "60-second demo"). The absence is itself an adoption blocker.

## 2. Current state

Open `README.md` and `nvim-poor-cli/README.md`. Note:
- TUI screenshots above the fold.
- Dual install paths (CLI + TUI + plugin), some retired.
- Multiplayer and archived Telegram/desktop not clearly deprecated.

## 3. Goal & non-goals

**Goal:** `README.md` reads as a Neovim-plugin README with the Python server/agent backend. First screen (above-the-fold) = value prop + one screenshot + install snippet. Dead references gone. New screenshots match current UX.

**Non-goals:**
- Do not create a full docs site (LONGTERM-TODO H4 is a separate effort).
- Do not rewrite `nvim-poor-cli/README.md` beyond alignment edits.
- Do not ship a full asciinema demo in this PRD — leave as a stretch.

## 4. Design

### 4.1 README structure (top-down)

1. Badges (keep).
2. Logo + one-line hook ("Provider-agnostic BYOK AI coding agent — Neovim-native, multiplayer-ready").
3. Screenshot (new v6).
4. Install (pip + lazy.nvim snippet, exact as in nvim-poor-cli/README).
5. Quickstart (3 steps: install, set `GEMINI_API_KEY`, `:PoorCliChat`).
6. Features (short bullets — link to docs for depth).
7. Model / provider support table.
8. Multiplayer (one paragraph + link to `docs/MULTIPLAYER.md`).
9. Commands link to plugin README rather than duplicating.
10. Contributing / license / acknowledgements.

### 4.2 Screenshots

Record these in v6/:
- `1.png` — Neovim with chat panel open mid-response.
- `2.png` — Diff Review panel in action (after PRD 014 lands; if not yet, reuse chat screenshot).
- `3.png` — Cost HUD + lualine (after PRD 016).
- `4.png` — Onboarding wizard step.
- `5.png` — Panels (tasks/checkpoints/sessions).

## 5. Files to create / modify / delete

**Create**
- `asset/reference/v6/*.png`

**Modify**
- `README.md` — full rewrite.
- `nvim-poor-cli/README.md` — remove/align anything that contradicts new top-level README.

**Delete**
- `asset/reference/v5/*.png` (or move to `asset/reference/archive/v5/`).

## 6. Implementation plan

1. Draft new `README.md` in a scratch file.
2. Record new screenshots (owner provides Neovim sessions; agent can generate placeholder images with labels if not available, marked `TODO: real screenshot`).
3. Replace `README.md`.
4. Delete old screenshots.
5. Grep for lingering references to TUI, Telegram, desktop, Emacs: `grep -rn "tui\|telegram\|desktop\|emacs" README.md docs/` — scrub.
6. Confirm badges and CI links still work.
7. `make lint && make test` (nothing code-level changed; sanity check only).

## 7. Testing & acceptance criteria

- README reads naturally above-the-fold.
- All links resolve.
- No references to archived clients.
- (Optional) CI has a markdown-lint step; PR passes if so.

**Done criterion**
- [ ] README rewritten.
- [ ] v5/ screenshots removed or archived.
- [ ] v6/ screenshots present (or clearly marked placeholders).
- [ ] No dead references to retired clients.

## 8. Rollback / risk

Zero. Docs only.

## 9. Out-of-scope & boundary

- 🚫 Do not create a documentation site.
- 🚫 Do not touch `docs/*.md` content (other than link fixes).
- 🚫 Do not ship an asciinema demo (defer).

## 10. Related PRDs & references

- LONGTERM-TODO C2, L6.
- LEARNING.md §1.1, §1.6.
- PRD 006 (_archived removal) pairs well.
