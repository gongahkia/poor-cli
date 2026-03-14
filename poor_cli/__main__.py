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


def _repo_binary_is_fresh(repo_root: Path, binary: Path) -> bool:
    if not binary.is_file() or not os.access(binary, os.X_OK):
        return False

    try:
        binary_mtime = binary.stat().st_mtime
    except OSError:
        return False

    watched_paths = [
        repo_root / "poor-cli-tui" / "Cargo.toml",
        repo_root / "poor-cli-tui" / "Cargo.lock",
    ]
    src_dir = repo_root / "poor-cli-tui" / "src"
    watched_paths.extend(path for path in src_dir.rglob("*") if path.is_file())

    try:
        return not any(path.stat().st_mtime > binary_mtime for path in watched_paths if path.exists())
    except OSError:
        return False


def _run_repo_tui_binary(argv: list[str]) -> int:
    repo_root = Path(__file__).resolve().parent.parent
    binary = repo_root / "poor-cli-tui" / "target" / "release" / "poor-cli-tui"
    if not _repo_binary_is_fresh(repo_root, binary):
        return 1
    os.execv(str(binary), [str(binary), *argv])
    return 1


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
    if _run_repo_tui_binary(argv) == 0:
        return
    if _run_tui_binary(argv) == 0:
        return
    if _run_tui_from_repo(argv) == 0:
        return
    raise SystemExit(
        "Rust TUI launcher not found. Run ./run_tui.sh from the repo root "
        "or install the `poor-cli-tui` binary. The Python package always "
        "provides `poor-cli-server`, but `poor-cli` requires a repo checkout "
        "or a preinstalled Rust TUI binary."
    )


if __name__ == "__main__":
    main()
