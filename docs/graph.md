# Graph Tools

Phase 2 starts with a tree-sitter-backed repo graph. The graph currently indexes Python, JavaScript, TypeScript, and TSX files and exposes symbol, import, caller, and neighborhood queries through replayable tools.

## Built-in Tools

- `find_symbol`: search indexed symbols by name.
- `definition_of`: return the first exact symbol definition.
- `imports_of`: return imports for a repo-relative Python path.
- `callers_of`: return files that call a symbol name.
- `subgraph`: return files connected to a symbol or path through imports and calls.

## Example

```sh
poor-cli run "inspect the parser flow" --graph --yes
```

Tool calls are recorded through the same `ToolDispatcher` cache as the v0 file/shell tools, so graph queries are replayable.
`--graph` is available on `plan` and `run`; it adds planner prompt bias toward `find_symbol`, `definition_of`, `callers_of`, `imports_of`, and `subgraph` before grep-based navigation.
Graph tools refresh the tree-sitter index before uncached queries when graph file mtimes or sizes change, reparsing only changed files and dropping deleted files.
`RepoGraph.watch()` starts a lightweight polling watcher for long-lived graph users that need updates before the next explicit tool query. `RepoGraph.watch(native=True)` uses `watchfiles`/Rust notify for native filesystem events on supported hosts.

## Scope

Remaining Phase 2 work:

- Token and correctness comparison against grep-mode on the fixed benchmark set.
- Additional grammars beyond Python, JavaScript, TypeScript, and TSX if the benchmark set needs them.
