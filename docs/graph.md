# Graph Tools

Phase 2 starts with a tree-sitter-backed Python repo graph. The graph currently indexes `.py` files and exposes symbol, import, caller, and neighborhood queries through replayable tools.

## Built-in Tools

- `find_symbol`: search indexed symbols by name.
- `definition_of`: return the first exact symbol definition.
- `imports_of`: return imports for a repo-relative Python path.
- `callers_of`: return files that call a symbol name.
- `subgraph`: return files connected to a symbol or path through imports and calls.

## Example

```sh
poor-cli run "use find_symbol and subgraph to inspect the parser flow" --yes
```

Tool calls are recorded through the same `ToolDispatcher` cache as the v0 file/shell tools, so graph queries are replayable.

## Scope

This is the first graph slice. Remaining Phase 2 work:

- Multi-language tree-sitter grammars.
- Incremental indexing on file watch.
- `--graph` mode prompt bias.
- Token and correctness comparison against grep-mode on the fixed benchmark set.
