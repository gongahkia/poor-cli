# PRD 006: Remove `_archived/` retired front-ends

- **Wave:** 1
- **Status:** ready
- **Owner (human):** @gongahkia
- **Estimated effort:** small (<1d)
- **Blocks:** —
- **Blocked by:** —
- **Files it mutates:** — (no edits, deletions only)
- **New files it adds:** —
- **Files it deletes:**
  - `_archived/emacs-poor-cli/` (recursive)
  - `_archived/poor-cli-desktop/` (recursive)
  - `_archived/poor-cli-telegram/` (recursive)
  - `_archived/poor-cli-tui/` (recursive)
  - `_archived/vscode-poor-cli/` (recursive)

## 1. Problem

`_archived/` holds five retired front-ends (Emacs, Desktop, Telegram bot, TUI, VS Code). The project consolidated to Neovim-only — these are unmaintained, take ~X MB of repo space, confuse contributors, and bloat clone time. LEARNING.md §1.1 notes the consolidation is correct; §1.6 recommends deletion.

## 2. Current state

```
$ ls _archived/
emacs-poor-cli  poor-cli-desktop  poor-cli-telegram  poor-cli-tui  vscode-poor-cli
```

None of these are imported by active code. Verify with:
```
grep -rn "_archived" poor_cli/ nvim-poor-cli/ tests/ Makefile pyproject.toml .github/
```

## 3. Goal & non-goals

**Goal:** `_archived/` is gone. Git history retains the last commits (via `git log` on the deleted paths). Nothing active references `_archived/`.

**Non-goals:**
- Do not re-home any of the archived code. If someone wants Emacs support back, they fork from the last commit that contained it.
- Do not delete the `asset/` directory (PRD 009 handles the stale screenshots).

## 4. Design

This is a delete-and-verify PRD. The single decision is whether to preserve a pointer for historians:

> **DECISION REQUIRED:** Should the project add a one-paragraph `_archived/README.md` pointing readers to the last commit hash that contained each archived front-end, for people who want to resurrect one? Options: (a) yes, keep `_archived/` with only a README pointing at `git log`, (b) delete `_archived/` entirely, (c) move the README to docs/ARCHIVED_CLIENTS.md. Owner to answer before execution.

Default if unanswered: **(b)**.

## 5. Files to create / modify / delete

**Delete**
- `_archived/emacs-poor-cli/` and everything under it.
- `_archived/poor-cli-desktop/` and everything under it.
- `_archived/poor-cli-telegram/` and everything under it.
- `_archived/poor-cli-tui/` and everything under it.
- `_archived/vscode-poor-cli/` and everything under it.
- If decision (b): `_archived/` itself.

**Modify** — only if grep finds a stale reference.

## 6. Implementation plan

1. Grep for `_archived` in every source file. Expect zero hits (other than docs). If there are hits in tests or Python, stop and ask the owner.
2. 🔴 Destructive: `git rm -r _archived/<subdir>` for each retired front-end. (Prefer `git rm` over `rm -rf` so git notices the deletion.)
3. If decision (a) or (c) above: write the pointer README.
4. Update `.gitignore` only if it had `_archived/` patterns (unlikely).
5. Search docs for broken links: `grep -rn "_archived\|archived/" docs/ *.md README.md` — remove or redirect them.
6. Run `make lint && make test` — should be unchanged.

## 7. Testing & acceptance criteria

**Commands**
- `make lint && make test` (nothing broke).
- `grep -rn "_archived" poor_cli/ nvim-poor-cli/ tests/ Makefile pyproject.toml` returns nothing.

**Done criterion**
- [ ] `_archived/` is gone or contains only the decision-(a/c) README.
- [ ] No source code or test references `_archived/`.
- [ ] CI green.

## 8. Rollback / risk

Low. Git history preserves everything. If someone needs an archived client, `git checkout <hash> -- _archived/<subdir>` restores it.

## 9. Out-of-scope & boundary

- 🚫 Do not touch `asset/`.
- 🚫 Do not rewrite README (PRD 009).
- 🚫 Do not remove `docs/` — even if it mentions archived clients, leave PRD 009 to rewrite.

## 10. Related PRDs

- PRD 009 (README rewrite) — naturally pairs with this.
- LEARNING.md §1.1, §1.6.
