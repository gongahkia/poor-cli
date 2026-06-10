"""Agent tool registry for repository and shell capabilities.

Each submodule registers its tools via ``register_tool`` from
``poor_cli.tools._registry``. The registry is consumed by
``core_tool_dispatch`` when the agent emits a tool call and by
``core_agent_loop`` when assembling the tool manifest for the provider.

Side-effect imports are added below as each tool family lands (B.2..B.5).
"""

from __future__ import annotations

from poor_cli.tools import _registry  # noqa: F401
from poor_cli.tools import git  # noqa: F401
from poor_cli.tools import debug  # noqa: F401
from poor_cli.tools import diagnostics  # noqa: F401
from poor_cli.tools import hunks  # noqa: F401
from poor_cli.tools import fs  # noqa: F401
from poor_cli.tools import task  # noqa: F401
from poor_cli.tools import deploy  # noqa: F401
from poor_cli.tools import watch  # noqa: F401
from poor_cli.tools import review  # noqa: F401
from poor_cli.tools import meta  # noqa: F401
from poor_cli.tools import tool_blob  # noqa: F401

__all__ = [
    "_registry", "git", "debug", "diagnostics", "hunks",
    "fs", "task", "deploy", "watch", "review", "meta", "tool_blob",
]
