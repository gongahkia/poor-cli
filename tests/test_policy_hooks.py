import json
import sys
from pathlib import Path

import pytest

from poor_cli.policy_hooks import PolicyHookManager


@pytest.mark.asyncio
async def test_policy_hooks_allow_and_deny_pre_tool_use(tmp_path: Path):
    hooks_dir = tmp_path / ".poor-cli" / "hooks"
    hooks_dir.mkdir(parents=True)
    hook_config = {
        "hooks": {
            "pre_tool_use": [
                {
                    "name": "allow-hook",
                    "command": sys.executable,
                    "args": [
                        "-c",
                        (
                            "import json, sys; payload=json.load(sys.stdin); "
                            "assert payload['toolName']=='write_file'; "
                            "print('allow')"
                        ),
                    ],
                },
                {
                    "name": "deny-hook",
                    "command": sys.executable,
                    "args": [
                        "-c",
                        (
                            "import json, sys; payload=json.load(sys.stdin); "
                            "sys.exit(1 if payload['toolName']=='write_file' else 0)"
                        ),
                    ],
                },
            ]
        }
    }
    (hooks_dir / "policy.json").write_text(json.dumps(hook_config), encoding="utf-8")

    manager = PolicyHookManager(tmp_path)
    results = await manager.run(
        "pre_tool_use",
        {"toolName": "write_file", "toolArgs": {"file_path": "demo.py"}},
    )

    assert len(results) == 2
    assert results[0].hook.name == "allow-hook"
    assert results[0].blocked is False
    assert results[1].hook.name == "deny-hook"
    assert results[1].blocked is True
    assert results[1].return_code != 0
