"""Launch poor-cli Rust TUI.

Python is retained for the backend JSON-RPC server (`poor_cli.server`).
The interactive CLI entrypoint is now the Rust TUI.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def _run_tui_from_repo(argv: list[str]) -> int:
    repo_root = Path(__file__).resolve().parent.parent
    script = repo_root / "run_tui.sh"
    if not script.is_file():
        return 1
    return subprocess.call([str(script), *argv], cwd=str(repo_root))


def _run_tui_binary(argv: list[str]) -> int:
    binary = shutil.which("poor-cli-tui")
    if binary is None:
        return 1
    os.execvp(binary, [binary, *argv])
    return 1


def main() -> None:
    argv = sys.argv[1:]
    if _run_tui_from_repo(argv) == 0:
        return
    _run_tui_binary(argv)
    raise SystemExit(
        "Rust TUI launcher not found. Run ./run_tui.sh from the repo root "
        "or install the `poor-cli-tui` binary."
    )


if __name__ == "__main__":
    main()
