#!/usr/bin/env python3
"""Report poor_cli modules not reachable from runtime entrypoints and tests."""

from __future__ import annotations

import ast
from collections import defaultdict, deque
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set

REPO_ROOT = Path(__file__).resolve().parents[1]
POOR_CLI_DIR = REPO_ROOT / "poor_cli"
TESTS_DIR = REPO_ROOT / "tests"

ENTRYPOINT_MODULES = {
    "poor_cli.repl_async",
    "poor_cli.server",
}


class ModuleRecord:
    def __init__(self, module: str, path: Path):
        self.module = module
        self.path = path


def iter_python_files(base: Path) -> Iterable[Path]:
    if not base.exists():
        return []
    return sorted(path for path in base.rglob("*.py") if path.is_file())


def module_name_from_path(path: Path) -> Optional[str]:
    try:
        relative = path.relative_to(REPO_ROOT)
    except ValueError:
        return None

    parts = list(relative.with_suffix("").parts)
    if not parts:
        return None

    if parts[-1] == "__init__":
        parts = parts[:-1]

    if not parts:
        return None

    return ".".join(parts)


def current_package(module_name: str, path: Path) -> str:
    if path.name == "__init__.py":
        return module_name
    if "." not in module_name:
        return ""
    return module_name.rsplit(".", 1)[0]


def resolve_relative_import(module_name: str, path: Path, level: int, imported_module: Optional[str]) -> Optional[str]:
    pkg = current_package(module_name, path)
    if not pkg:
        return None

    pkg_parts = pkg.split(".")
    if level <= 0 or level > len(pkg_parts) + 1:
        return None

    # level=1 means current package, level=2 means one parent, etc.
    prefix_len = len(pkg_parts) - (level - 1)
    if prefix_len < 0:
        return None

    prefix = pkg_parts[:prefix_len]
    if imported_module:
        prefix.extend(imported_module.split("."))

    if not prefix:
        return None

    return ".".join(prefix)


def collect_project_modules() -> Dict[str, ModuleRecord]:
    records: Dict[str, ModuleRecord] = {}
    for root in (POOR_CLI_DIR, TESTS_DIR):
        for path in iter_python_files(root):
            module_name = module_name_from_path(path)
            if module_name:
                records[module_name] = ModuleRecord(module_name, path)
    return records


def extract_imports(record: ModuleRecord, known_modules: Set[str]) -> Set[str]:
    imports: Set[str] = set()

    try:
        tree = ast.parse(record.path.read_text(encoding="utf-8"), filename=str(record.path))
    except SyntaxError:
        return imports

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                target = alias.name
                if target in known_modules:
                    imports.add(target)
                # Include package module if importing submodule path.
                parent = target
                while "." in parent:
                    parent = parent.rsplit(".", 1)[0]
                    if parent in known_modules:
                        imports.add(parent)

        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                base = resolve_relative_import(record.module, record.path, node.level, node.module)
            else:
                base = node.module

            if not base:
                continue

            if base in known_modules:
                imports.add(base)

            for alias in node.names:
                if alias.name == "*":
                    continue
                candidate = f"{base}.{alias.name}"
                if candidate in known_modules:
                    imports.add(candidate)

    return imports


def build_graph(records: Dict[str, ModuleRecord]) -> Dict[str, Set[str]]:
    known_modules = set(records.keys())
    graph: Dict[str, Set[str]] = defaultdict(set)

    for module_name, record in records.items():
        graph[module_name] = extract_imports(record, known_modules)

    return graph


def traverse_reachable(graph: Dict[str, Set[str]], roots: Iterable[str]) -> Set[str]:
    visited: Set[str] = set()
    queue = deque(root for root in roots if root in graph)

    while queue:
        module = queue.popleft()
        if module in visited:
            continue
        visited.add(module)
        for neighbor in graph.get(module, set()):
            if neighbor not in visited:
                queue.append(neighbor)

    return visited


def main() -> int:
    records = collect_project_modules()
    graph = build_graph(records)

    test_roots = {name for name in records if name.startswith("tests.")}
    roots = set(ENTRYPOINT_MODULES) | test_roots
    reachable = traverse_reachable(graph, roots)

    poor_cli_modules = sorted(name for name in records if name.startswith("poor_cli."))
    unreachable = [name for name in poor_cli_modules if name not in reachable]

    print("Import Graph Report")
    print(f"Entry roots: {', '.join(sorted(ENTRYPOINT_MODULES))}")
    print(f"Test roots: {len(test_roots)} modules")
    print(f"Reachable poor_cli modules: {len(poor_cli_modules) - len(unreachable)} / {len(poor_cli_modules)}")

    if not unreachable:
        print("No unreachable poor_cli modules detected.")
        return 0

    print("Unreachable poor_cli modules (no import path from entrypoints/tests):")
    for module_name in unreachable:
        print(f"- {module_name}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
