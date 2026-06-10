"""CI guard for archived module imports."""

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARCHIVED_MODULES = {
    "poor_cli.speculative_decoding": {"poor_cli.speculative_decoding", "speculative_decoding"},
}


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def test_archived_modules_are_not_imported_by_runtime_code() -> None:
    archived_aliases = set().union(*ARCHIVED_MODULES.values())
    for module in ARCHIVED_MODULES:
        module_path = ROOT / Path(*module.split(".")).with_suffix(".py")
        assert not module_path.exists()
    offenders = []
    for path in (ROOT / "poor-cli").rglob("*.py"):
        found = archived_aliases & _imported_modules(path)
        if found:
            offenders.append((path.relative_to(ROOT), sorted(found)))
    assert offenders == []
