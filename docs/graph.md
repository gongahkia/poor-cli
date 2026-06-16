# Graph Tools

Phase 2 starts with a tree-sitter-backed repo graph. The graph indexes Python, JavaScript, TypeScript, and TSX-family files and exposes symbol, import, caller, and neighborhood queries through replayable tools.

## Language Matrix

| Language | Extensions | Parser package | Status |
| --- | --- | --- | --- |
| Python | `.py` | `tree_sitter_python` | supported |
| JavaScript | `.js`, `.mjs`, `.cjs` | `tree_sitter_javascript` | supported |
| TypeScript | `.ts`, `.tsx`, `.mts`, `.cts` | `tree_sitter_typescript` | supported |
| Other languages | any other extension | none | unsupported; use grep/manual context |

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
`plan`, `run`, RPC, and swarm auto-enable graph mode when the goal names files, symbols, imports, callers, call paths, parser/test flow, or multi-file code behavior. `--graph` still forces graph mode explicitly.
Graph mode also adds a bounded graph-context summary to the planner prompt and per-task context packet. The summary records matching symbols, imports, callers, parser dependency status, and any graph fallback warning as a `graph.context` artifact.
If graph indexing is unavailable, the run records a `graph.fallback` artifact and proceeds with grep/manual-context guidance.
Graph tools refresh the tree-sitter index before uncached queries when graph file mtimes or sizes change, reparsing only changed files and dropping deleted files.
`RepoGraph.watch()` starts a lightweight polling watcher for long-lived graph users that need updates before the next explicit tool query. `RepoGraph.watch(native=True)` uses `watchfiles`/Rust notify for native filesystem events on supported hosts.
`poor-cli doctor` and `poor-cli agents doctor` report parser dependency availability. If graph tools cannot build an index inside a tool call, they return an explicit grep fallback warning in the tool result instead of hiding the failure.

## Benchmark

```sh
python bench/graph_vs_grep.py --output bench/results/graph-vs-grep-synthetic.json
```

The benchmark reports latency, recall proxy, context lines, and token-count proxy for graph mode versus grep mode.

## Scope

Additional grammars are out of scope unless the benchmark set needs them.
