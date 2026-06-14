# Hooks

Hooks are Python entry points that observe lifecycle events without changing core runtime code.

Register hooks with the `poor_cli.hooks` entry-point group. A hook object can implement any methods from `poor_cli.hooks.Hook`:

```python
from collections.abc import Mapping
from typing import Any


class AuditHook:
    def before_turn(self, context: Mapping[str, Any]) -> None:
        ...

    def after_tool_call(self, context: Mapping[str, Any], result: Any) -> None:
        ...

    def before_model_call(self, context: Mapping[str, Any]) -> None:
        ...

    def after_run(self, context: Mapping[str, Any]) -> None:
        ...
```

`BaseHook` provides no-op defaults when a hook only needs one callback.

## Entry Point

```toml
[project.entry-points."poor_cli.hooks"]
audit = "my_package.audit:AuditHook"
```

Hook loading is fail-fast. If an entry point cannot load, `HookLoadError` stops startup instead of silently dropping instrumentation.

## Current Contexts

- Tool callbacks receive `run_id`, `tool`, `request_hash`, `task_id`, and `cached`.
- Provider callbacks receive `run_id`, `provider`, `model`, and `request_hash`.
- Run callbacks receive the context supplied by the orchestrator.
