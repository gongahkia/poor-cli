# Auto-commit mode

poor-cli can auto-commit every AI file mutation so `git revert` gives you free undo. Pairs well with the checkpoint system (checkpoints snapshot disk state; auto-commits snapshot history).

## Enable

```yaml
# ~/.poor-cli/config.yaml
agentic:
  auto_commit: true
```

Or at runtime: `/set agentic.auto_commit true`.

## Behavior

- After every `write_file` / `edit_file` that actually mutates content:
    1. `git add -- <file>` stages the file.
    2. `git diff --cached --shortstat` captures line delta.
    3. `git commit -m "AI: <verb> <N> lines in <rel_path>"` creates the commit.
- Verb is `create` for brand-new files, `update` for edits.
- Line count comes from the staged shortstat (insertions + deletions).
- Skips when:
    - Not a git repo.
    - File matches `.gitignore`.
    - Staged diff is empty (write produced identical content).

## Examples

```
AI: create 24 lines in src/auth.py
AI: update 8 lines in README.md
AI: update 1 line in pyproject.toml
```

## With worktrees

poor-cli's task system (`/task`) isolates long-running AI work in `git worktree`s under `.poor-cli/worktrees/`. Auto-commit in a worktree lands commits on the worktree's branch, not the main branch. Merging the worktree branch is a separate `/task approve` step.

## Reverting

Because every mutation is a commit, revert is ordinary:

```
git revert HEAD           # undo the latest AI change
git revert HEAD~3..HEAD   # undo the last 3 AI changes
```

Or use poor-cli's `/undo` (restores the last checkpoint, which usually corresponds to a batch of commits).

## When NOT to enable

- Dirty working tree with unrelated WIP — auto-commit will happily snapshot your staged changes into an AI commit.
- Team branches where you want AI edits to remain uncommitted until reviewed — use Diff Review (`:PoorCLIDiffReview`) instead.
- Squash-merge workflows — each AI step becomes a commit; pre-PR squash may be desirable.

## See Also

- `docs/phase_14_nvim_observability_panels.md` Agent 14A — Diff Review panel, the alternative to auto-commit.
- `CHECKPOINTS.md` (if it exists) — checkpoint system details.
- `HARNESS_PORTABILITY.md` — why every mutation is local + reconstructible.
