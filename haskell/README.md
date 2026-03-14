# `seuss-hs`

Parallel Haskell rewrite of `seuss`.

This package introduces:

- a `megaparsec`-based parser for the current DSL surface
- a pure evaluator and validation pipeline
- semantic diffing and SVG export
- a `brick`-based analytical terminal UI shell
- importer scaffolding for CSV, GEDCOM, and JSON-LD

## Planned build flow

Once `ghc` and `cabal` are installed locally:

```console
$ cd haskell
$ cabal build
$ cabal run seuss -- check ../examples/lotr.seuss
$ cabal run seuss -- run ../examples/lotr.seuss
$ cabal test
```

## Current command coverage

- `run <file>` opens the Brick-based analytical TUI.
- `check <file>` parses, evaluates, and validates a `.seuss` file.
- `diff <file1> <file2>` reports timeline, entity, and relationship deltas.
- `import <file> --from csv|gedcom|jsonld` converts external sources into `.seuss`.
- `repl` supports `:load`, `:files`, `:world`, `:entities`, `:rels`, and `:validate`.
- `export <file> -f svg` writes an SVG using the shared layout engine.

`png` and `pdf` are accepted at the CLI surface but still intentionally fail with an explicit message until those backends are ported.

## Current language coverage additions

- `if`, `else if`, and `else` conditional chains now parse and evaluate.
- `match <expr> { ... }` statements now parse and evaluate with literal, identifier-bind, and `_` wildcard arms.
- list literals like `["one", "two"]` and integer range expressions like `1..3` now parse and evaluate.
- `for` loops can now iterate over bound list and range expressions, not just inline literals.
- `let mut name = ...;` is accepted, and existing bindings can now be reassigned with `name = ...;`.
- `for` loops support explicit list iterables like `[1, 2, 3]` and integer ranges like `1..3`.
- `repeat <count> { ... }` loops now parse and evaluate.
- `while <condition> { ... }` loops now parse and evaluate with a hard safety limit.
- `import "path";` statements are parsed, and the loader inlines imported files recursively before evaluation.

## Current TUI additions

- `?` toggles a help panel.
- `c` cycles a comparison target timeline and shows a delta summary in the inspector.
- `b` stores the currently selected entity into the next bookmark slot.
- `1`-`9` jump to saved entity bookmarks.
- `u` and `y` undo or redo view-state changes.

## Config shape

The Haskell loader currently understands a minimal TOML-like config format:

```toml
[export]
default_width = 1920
default_height = 1080
default_format = "svg"

[theme]
name = "light"
background = "#ffffff"
text = "#111827"
timeline = "#2563eb"
entity = "#059669"
relationship = "#d97706"
```

`--theme dark`, `--theme light`, and `--theme path/to/theme.toml` are supported for SVG export.
