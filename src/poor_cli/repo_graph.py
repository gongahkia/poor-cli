from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

GraphSignature = tuple[int, int]
GraphFingerprint = dict[str, GraphSignature]


@dataclass(frozen=True)
class GraphSymbol:
    name: str
    kind: str
    path: str
    line_start: int
    line_end: int
    scope: str = ""


@dataclass(frozen=True)
class ParsedModule:
    path: str
    symbols: list[GraphSymbol]
    imports: list[str]
    calls: list[str]


class RepoGraphError(RuntimeError):
    pass


class RepoGraph:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.modules: dict[str, ParsedModule] = {}
        self._symbol_index: dict[str, list[GraphSymbol]] = {}
        self._fingerprint: GraphFingerprint = {}

    def build_index(self) -> RepoGraph:
        modules = {}
        files = self._python_files()
        for path in files:
            module = _parse_python(self.root, path)
            modules[module.path] = module
        self.modules = modules
        self._rebuild_symbol_index()
        self._fingerprint = self._fingerprint_for(files)
        return self

    def refresh_if_stale(self) -> RepoGraph:
        current = self._scan_fingerprint()
        if current == self._fingerprint:
            return self
        if not self.modules:
            return self.build_index()
        changed = [self.root / path for path, signature in current.items() if self._fingerprint.get(path) != signature]
        removed = set(self._fingerprint) - set(current)
        for rel_path in removed:
            self.modules.pop(rel_path, None)
        for file_path in changed:
            module = _parse_python(self.root, file_path)
            self.modules[module.path] = module
        self._rebuild_symbol_index()
        self._fingerprint = current
        return self

    def _rebuild_symbol_index(self) -> None:
        self._symbol_index = {}
        for module in self.modules.values():
            for symbol in module.symbols:
                self._symbol_index.setdefault(symbol.name, []).append(symbol)

    def find_symbol(self, query: str, *, max_results: int = 20) -> list[dict[str, Any]]:
        needle = query.lower()
        matches = [
            symbol
            for symbols in self._symbol_index.values()
            for symbol in symbols
            if not needle or needle in symbol.name.lower() or needle in f"{symbol.scope}.{symbol.name}".lower()
        ]
        return [asdict(symbol) for symbol in sorted(matches, key=lambda item: (item.path, item.line_start, item.name))[:max_results]]

    def definition_of(self, symbol_name: str) -> dict[str, Any] | None:
        symbols = self._symbol_index.get(symbol_name, [])
        return asdict(sorted(symbols, key=lambda item: (item.path, item.line_start))[0]) if symbols else None

    def imports_of(self, path: str) -> dict[str, Any]:
        module = self._module(path)
        return {"path": module.path, "imports": module.imports}

    def callers_of(self, symbol_name: str, *, max_results: int = 20) -> list[dict[str, Any]]:
        callers = []
        for module in self.modules.values():
            if symbol_name in module.calls:
                callers.append({"path": module.path, "calls": symbol_name, "call_count": module.calls.count(symbol_name)})
        return sorted(callers, key=lambda item: (str(item["path"]), int(str(item["call_count"]))))[:max_results]

    def subgraph(self, seed: str, *, max_depth: int = 1) -> dict[str, Any]:
        start_paths = {seed} if seed in self.modules else {symbol.path for symbol in self._symbol_index.get(seed, [])}
        seen_paths: set[str] = set()
        frontier = set(start_paths)
        for _ in range(max(0, max_depth) + 1):
            next_frontier: set[str] = set()
            for path in frontier:
                if path in seen_paths or path not in self.modules:
                    continue
                seen_paths.add(path)
                module = self.modules[path]
                for imported in module.imports:
                    resolved = self._resolve_import(module.path, imported)
                    if resolved and resolved not in seen_paths:
                        next_frontier.add(resolved)
                for call in module.calls:
                    for symbol in self._symbol_index.get(call, []):
                        if symbol.path not in seen_paths:
                            next_frontier.add(symbol.path)
            frontier = next_frontier
        return {
            "seed": seed,
            "files": [
                {
                    "path": path,
                    "symbols": [asdict(symbol) for symbol in self.modules[path].symbols],
                    "imports": self.modules[path].imports,
                }
                for path in sorted(seen_paths)
            ],
        }

    def _module(self, path: str) -> ParsedModule:
        normalized = str(Path(path))
        if normalized not in self.modules:
            raise RepoGraphError(f"unknown graph path: {path}")
        return self.modules[normalized]

    def _resolve_import(self, from_path: str, imported: str) -> str | None:
        candidate = imported.replace(".", "/") + ".py"
        if candidate in self.modules:
            return candidate
        base = str(Path(from_path).parent / (imported.rsplit(".", 1)[-1] + ".py"))
        return base if base in self.modules else None

    def _scan_fingerprint(self) -> GraphFingerprint:
        return self._fingerprint_for(self._python_files())

    def _python_files(self) -> list[Path]:
        return sorted(path for path in self.root.rglob("*.py") if "__pycache__" not in path.parts and path.is_file())

    def _fingerprint_for(self, paths: Iterable[Path]) -> GraphFingerprint:
        rows = {}
        for path in paths:
            try:
                stat = path.stat()
            except FileNotFoundError:
                continue
            rows[str(path.resolve().relative_to(self.root))] = (stat.st_mtime_ns, stat.st_size)
        return rows


def graph_tools(root: Path) -> dict[str, Any]:
    graph = RepoGraph(root).build_index()
    return {
        "find_symbol": lambda args: _tool_result(
            "find_symbol",
            graph.refresh_if_stale().find_symbol(str(args.get("query") or ""), max_results=int(args.get("max_results") or 20)),
        ),
        "definition_of": lambda args: _tool_result("definition_of", graph.refresh_if_stale().definition_of(str(args.get("symbol") or ""))),
        "imports_of": lambda args: _tool_result("imports_of", graph.refresh_if_stale().imports_of(str(args.get("path") or ""))),
        "callers_of": lambda args: _tool_result(
            "callers_of",
            graph.refresh_if_stale().callers_of(str(args.get("symbol") or ""), max_results=int(args.get("max_results") or 20)),
        ),
        "subgraph": lambda args: _tool_result(
            "subgraph",
            graph.refresh_if_stale().subgraph(str(args.get("seed") or ""), max_depth=int(args.get("max_depth") or 1)),
        ),
    }


def _parse_python(root: Path, path: Path) -> ParsedModule:
    try:
        import tree_sitter_python
        from tree_sitter import Language, Parser
    except ImportError as exc:
        raise RepoGraphError("tree-sitter and tree-sitter-python are required for repo graph indexing") from exc

    source = path.read_bytes()
    parser = Parser()
    language = Language(tree_sitter_python.language())
    parser.language = language
    tree = parser.parse(source)
    if tree is None:
        raise RepoGraphError(f"tree-sitter failed to parse {path}")
    rel = str(path.resolve().relative_to(root))
    payload = _walk_python(source, tree.root_node)
    return ParsedModule(
        path=rel,
        symbols=[GraphSymbol(path=rel, **symbol) for symbol in payload["symbols"]],
        imports=payload["imports"],
        calls=payload["calls"],
    )


def _walk_python(source: bytes, root: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"symbols": [], "imports": [], "calls": []}

    def text(node: Any) -> str:
        return source[node.start_byte : node.end_byte].decode("utf-8", "ignore")

    def first_identifier(node: Any) -> Any:
        if node.type == "identifier":
            return node
        for child in getattr(node, "children", []):
            found = first_identifier(child)
            if found is not None:
                return found
        return None

    def last_identifier(node: Any) -> Any:
        if node.type == "identifier":
            return node
        for child in reversed(getattr(node, "children", [])):
            found = last_identifier(child)
            if found is not None:
                return found
        return None

    def add_symbol(node: Any, name: str, kind: str, scope: str = "") -> None:
        payload["symbols"].append(
            {
                "name": name,
                "kind": kind,
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "scope": scope,
            }
        )

    def visit(node: Any, scope: str = "") -> None:
        if node.type == "import_statement":
            statement = text(node)
            for part in statement.removeprefix("import").split(","):
                name = part.strip().split(" as ", 1)[0]
                if name:
                    payload["imports"].append(name)
            return
        if node.type == "import_from_statement":
            statement = text(node)
            if statement.startswith("from ") and " import " in statement:
                payload["imports"].append(statement[5:].split(" import ", 1)[0].strip())
            return
        if node.type == "class_definition":
            name_node = node.child_by_field_name("name") or first_identifier(node)
            name = text(name_node) if name_node is not None else ""
            if name:
                add_symbol(node, name, "class")
            for child in getattr(node, "children", []):
                visit(child, name)
            return
        if node.type in {"function_definition", "async_function_definition"}:
            name_node = node.child_by_field_name("name") or first_identifier(node)
            name = text(name_node) if name_node is not None else ""
            if name:
                add_symbol(node, name, "method" if scope else "function", scope)
            for child in getattr(node, "children", []):
                visit(child, scope)
            return
        if node.type == "call":
            callee = last_identifier(getattr(node, "children", [None])[0])
            if callee is not None:
                payload["calls"].append(text(callee))
        for child in getattr(node, "children", []):
            visit(child, scope)

    visit(root)
    return payload


def _tool_result(name: str, output: Any) -> Any:
    from poor_cli.tools.dispatcher import ToolResult

    return ToolResult(name=name, ok=True, output=output)
