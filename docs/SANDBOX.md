# Sandbox Presets

poor-cli's tools (especially `bash`, `write_file`, `delete_file`, `apply_patch_unified`) execute under a sandbox layer. The preset controls how strictly that layer constrains the agent.

## Presets

| Preset | Filesystem | Network | Process | Use when |
|---|---|---|---|---|
| `restrictive` | read-only repo | none | none | Code review, exploration only. |
| `moderate` | read + write under repo | local-only (loopback) | spawn within repo | Default for most users. |
| `permissive` | read + write anywhere | full | full | Power-user CI scripts you fully trust. |
| `none` | no enforcement (legacy) | full | full | Discouraged. Some tests need this. |

Switch interactively: `/sandbox restrictive` etc. Persists in `~/.poor-cli/config.yaml` under `sandbox.preset`.

The active preset shows on the lualine segment + `/status`.

## What each layer enforces

### Filesystem

- Reads outside the repo trigger an audit log entry; writes outside the repo are blocked unless `permissive`.
- Path traversal (`../../etc/passwd`) is blocked on every preset including `none` (this is unicode-safety, not sandbox).
- Symlink resolution: writes follow symlinks only when target is inside the repo.

### Network

- `restrictive`: no outbound network. `fetch_url` returns a sandbox-denied error.
- `moderate`: loopback + same-host only. Useful for talking to local Ollama / preview server.
- `permissive`: full outbound. SSRF protection (block 169.254.x, link-local, etc.) is always on.

### Process

- `restrictive`: no subprocess spawning. `bash` returns sandbox-denied.
- `moderate`: spawn within repo cwd; some commands like `rm -rf` outside repo are blocked.
- `permissive`: anything goes.

## Per-tool capability declarations

`tools_async.DEFAULT_TOOL_CAPABILITIES` declares which sandbox capabilities each tool needs. The sandbox layer rejects a call when the active preset doesn't grant the required capability.

Example:
```python
DEFAULT_TOOL_CAPABILITIES = {
    "read_file": ["fs_read"],
    "write_file": ["fs_write"],
    "bash": ["process_spawn", "fs_read", "fs_write"],
    "fetch_url": ["network_outbound"],
    ...
}
```

Adding a new tool? Declare its capabilities in `_tool_registry_builder.py`.

## OS-level sandbox (optional)

Beyond the in-process sandbox, poor-cli can wrap subprocess execution under OS-level isolation:

- **macOS**: `sandbox-exec` profile in `poor_cli/sandbox.py`. Activated automatically when `sandbox.os_level: true` and OS is macOS.
- **Linux**: namespace-based isolation via `unshare`. Same flag.
- **Docker**: full container isolation. Requires `docker_sandbox.enabled: true` AND a Docker daemon. Slowest, most complete. See `docker_sandbox.py`.

Tested in `tests/test_sandbox_os_level.py` + `tests/test_linux_sandbox.py`.

## Permission rules

`.poor-cli/permissions.yaml` lets you whitelist or blacklist specific tool calls:

```yaml
rules:
  - name: never run rm -rf
    tool: bash
    deny:
      command_pattern: "rm\\s+-rf"

  - name: allow git only
    tool: bash
    allow:
      command_pattern: "^git\\s+"

  - name: scope edits to src/
    tool: edit_file
    allow:
      file_path_pattern: "^src/"
```

Rules are evaluated by `permission_engine.py`; the Trust Center (`:PoorCLITrustCenter`) and Policy Panel (`:PoorCLIPolicy`) render the active rule set.

## Auto-approve / deny patterns

For headless / CI use, `agentic.auto_approve_tools` and `agentic.deny_patterns` skip interactive confirmation:

```yaml
agentic:
  auto_approve_tools: ["read_file", "glob_files", "grep_files", "git_status", "git_diff"]
  deny_patterns: ["rm -rf", "force-push", "drop database"]
```

Useful for `poor-cli exec` non-interactive runs. Don't use in interactive sessions unless you've reviewed the patterns carefully.

## Audit log

Every sandbox decision (allow + deny) writes a row to `.poor-cli/audit.db`. Inspect with:

- `/audit-export --since 2026-04-01 --to recent.jsonl`
- The Trust Center buffer.

Audit logs rotate at 100 MB (configurable in `audit.size_limit_mb`), with monthly archives in `.poor-cli/audit/archive/YYYY-MM.jsonl.gz`.

## See also

- [HARNESS_PORTABILITY.md](./HARNESS_PORTABILITY.md) — why local-first matters.
- [PROVIDERS.md](./PROVIDERS.md) — the credentials sandbox sits in front of.
