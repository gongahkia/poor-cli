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
