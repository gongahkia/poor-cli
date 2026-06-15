# Worktree Swarm

`poor-cli run-swarm` plans a goal, creates detached `git worktree` workers, runs each task in isolation, and collects worker artifacts.

## Commands

```sh
poor-cli plan "split this fix" --emit-tasks
poor-cli run-swarm "split this fix" --parallel 2
poor-cli cleanup-swarm <run_id>
```

## Policy

- Main worktree dirtiness refuses swarm startup unless `--allow-dirty` is set.
- Worker paths live under `.poor-cli/v6/runs/<run_id>/worktrees/`.
- Worker artifacts include `PATCH.diff`, `RESULT.md`, `changed-files.json`, and `swarm.worker` metadata.
- Merge is collect-only by default. `merge/MERGE_PLAN.json` orders non-conflicting patches and records conflicts as review tasks.
- `cleanup-swarm` removes recorded run-owned worktrees and preserves artifacts, CAS blobs, and replay events.
