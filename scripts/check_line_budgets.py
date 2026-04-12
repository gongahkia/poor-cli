#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fnmatch
import os
import sys
from pathlib import Path

DEFAULT_LIMIT_KEY = "__default__"
LINE_LIMITS = {
    "poor_cli/core.py": 1_000,
    "poor_cli/server/runtime.py": 800,
    "poor_cli/server/handlers/*.py": 500,
    "poor_cli/config.py": 1_500,
    # Existing monoliths outside Phase 9; reviewers can lower these after their split PRDs.
    "poor_cli/tools_async.py": 4_300,
    "poor_cli/multiplayer.py": 2_150,
    "poor_cli/core_turn_lifecycle.py": 2_700,
    DEFAULT_LIMIT_KEY: 2_000,
}

EXCLUDED_DIRS = {
    ".git",
    ".mypy_cache",
    ".nox",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "generated",
    "node_modules",
    "tests",
    "vendor",
    "vendored",
    "venv",
}
GENERATED_FILE_PATTERNS = (
    "*_pb2.py",
    "*_pb2_grpc.py",
    "*.generated.py",
    "*.gen.py",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="check Python file line budgets")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    return parser.parse_args()


def count_lines(path: Path) -> int:
    with path.open(encoding="utf-8", errors="replace") as handle:
        return sum(1 for _ in handle)


def is_excluded(path: Path, repo_root: Path) -> bool:
    rel = path.relative_to(repo_root)
    if any(part in EXCLUDED_DIRS for part in rel.parts[:-1]):
        return True
    return any(path.match(pattern) for pattern in GENERATED_FILE_PATTERNS)


def iter_python_files(repo_root: Path) -> list[Path]:
    files: list[Path] = []
    for root, dirs, filenames in os.walk(repo_root):
        dirs[:] = [dirname for dirname in dirs if dirname not in EXCLUDED_DIRS]
        for filename in filenames:
            path = Path(root) / filename
            if path.suffix == ".py" and not is_excluded(path, repo_root):
                files.append(path)
    return files


def format_error(path: str, line_count: int, limit: int) -> str:
    return f"{path} {line_count}/{limit} (+{line_count - limit})"


def limit_for(rel_path: str, default_limit: int) -> int:
    for pattern, limit in LINE_LIMITS.items():
        if pattern == DEFAULT_LIMIT_KEY:
            continue
        if fnmatch.fnmatch(rel_path, pattern):
            return limit
    return default_limit


def main() -> int:
    repo_root = parse_args().root.resolve()
    errors: list[str] = []

    default_limit = LINE_LIMITS[DEFAULT_LIMIT_KEY]

    for rel_path, limit in LINE_LIMITS.items():
        if rel_path == DEFAULT_LIMIT_KEY or any(char in rel_path for char in "*?["):
            continue
        path = repo_root / rel_path
        if not path.exists():
            continue
        line_count = count_lines(path)
        if line_count > limit:
            errors.append(format_error(rel_path, line_count, limit))

    for path in iter_python_files(repo_root):
        rel_path = path.relative_to(repo_root).as_posix()
        if rel_path in LINE_LIMITS and not any(char in rel_path for char in "*?["):
            continue
        limit = limit_for(rel_path, default_limit)
        line_count = count_lines(path)
        if line_count > limit:
            errors.append(format_error(rel_path, line_count, limit))

    for error in errors:
        path = error.split(" ", 1)[0]
        print(f"::error file={path}::{error}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
