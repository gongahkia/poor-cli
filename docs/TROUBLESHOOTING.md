# Troubleshooting

## Command not found

```sh
python3 -m pip install --upgrade 'poor-cli[all]'
python3 -m poor_cli help
```

If `poor-cli` is still missing, inspect the Python scripts path:

```sh
python3 -m site --user-base
```

Add the matching `bin` directory to `PATH`.

## Provider key missing

Set an environment variable or use the key manager:

```sh
export ANTHROPIC_API_KEY="..."
export OPENAI_API_KEY="..."
export GEMINI_API_KEY="..."
poor-cli provider list
```

`poor-cli diag doctor` reports detected provider configuration.

## Chat starts but provider import fails

Install the needed extra:

```sh
python3 -m pip install 'poor-cli[anthropic]'
python3 -m pip install 'poor-cli[openai]'
python3 -m pip install 'poor-cli[all]'
```

## CI run hangs

Use `exec` in non-interactive jobs:

```sh
poor-cli exec --prompt "run focused tests and report failures"
```

Set explicit tool policy for unattended runs:

```yaml
agentic:
  auto_approve_tools: ["read_file", "glob_files", "grep_files", "git_status", "git_diff"]
  deny_patterns: ["rm -rf", "force-push"]
```

## Sandbox denied a command

Inspect current mode:

```sh
poor-cli help
```

Then adjust `~/.poor-cli/config.yaml` or repo-local `.poor-cli/config.yaml`:

```yaml
sandbox:
  preset: moderate
```

Use `permissive` only for trusted local runs.

## State looks stale

Repo-local state lives in `.poor-cli/`. Inspect before deleting:

```sh
find .poor-cli -maxdepth 2 -type f | sort
```

Checkpoints and audit logs may be useful for rollback.

## Debug checklist

```sh
python3 -m compileall poor_cli
python3 -m pytest -q
python3 -m poor_cli help
python3 -m poor_cli exec --help
python3 -m poor_cli install info
```
