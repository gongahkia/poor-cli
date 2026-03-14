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
- `lsp` runs a minimal stdio language server with diagnostics, hover, and keyword completion.
- `export <file> -f svg` writes an SVG using the shared layout engine.

`png` and `pdf` are accepted at the CLI surface but still intentionally fail with an explicit message until those backends are ported.

## Current importer additions

- CSV import now accepts header aliases like `id`, `entity_type`, `lane`, `track`, `from`, and `to`.
- CSV entity imports now synthesize timeline declarations, sanitize generated identifiers, and preserve booleans, numbers, and ISO dates as typed literals.
- GEDCOM import now keeps family structure by emitting `spouse` and `parent_of` relationships in addition to person entities.
- JSON-LD import now turns `@id` references inside object properties and arrays into Seuss relationships instead of flattening them into opaque fields.

## Current language coverage additions

- `if`, `else if`, and `else` conditional chains now parse and evaluate.
- `match <expr> { ... }` statements now parse and evaluate with literal, identifier-bind, and `_` wildcard arms.
- list literals like `["one", "two"]` and integer range expressions like `1..3` now parse and evaluate.
- postfix index expressions like `labels[1]` and `"abc"[1]` now parse and evaluate.
- function declarations now accept optional return annotations like `fn add(a: int, b: int) -> int { ... }`.
- explicit `return` statements now parse and short-circuit function bodies, including returns from inside loop bodies.
- named function calls now evaluate with scoped parameter binding, return the last expression in the body, and also work as standalone statement calls.
- typed closures like `|x: int| x + offset` now parse and evaluate with captured outer bindings.
- a first builtin set is now wired up in the Haskell runtime: `len`, `before`, `after`, and `type_of`.
- dot-based field access like `frodo.age` and `main.kind` now resolves against entity and timeline values already present in the world.
- type declarations now parse optional fields like `age: int?` and metadata entries like `@title: "Leader"`.
- entity field access now falls back through type metadata inheritance when the field is not set directly on the entity.
- `let name: type = ...;` annotations now parse and are shallowly enforced for let bindings, function arguments, and function returns.
- `for` loops can now iterate over bound list and range expressions, not just inline literals.
- `let mut name = ...;` is accepted, and existing bindings can now be reassigned with `name = ...;`.
- boolean logic now includes `&&` and `||`, and comparisons now include `!=`, `<=`, and `>=`.
- `for` loops support explicit list iterables like `[1, 2, 3]` and integer ranges like `1..3`.
- `repeat <count> { ... }` loops now parse and evaluate.
- `while <condition> { ... }` loops now parse and evaluate with a hard safety limit.
- `import "path";` statements are parsed, and the loader inlines imported files recursively before evaluation.

## Current TUI additions

- `?` toggles a help panel.
- `Enter` follows the current selection: timelines jump into their entities, entities open neighborhood relationships, and relationships jump back to entities.
- `c` cycles a comparison target timeline and shows a delta summary in the inspector.
- `b` stores the currently selected entity into the next bookmark slot.
- `1`-`9` jump to saved entity bookmarks.
- `s` and `g` jump from a selected relationship to its source or target entity.
- `:` opens a small command palette with actions like `help`, `compare`, `bookmark`, `clear-search`, `clear-filters`, `follow`, `rel-source`, `rel-target`, `clear-scrub`, `scrub-center`, `timeline-next`, and `timeline-prev`.
- `[` and `]` step a time scrubber that filters visible entities and relationships to the selected point in time.
- `{` and `}` jump the scrubber to the selected timeline’s start or end boundary.
- `u` and `y` undo or redo view-state changes.
- The inspector now keeps a short recent-selection trail so users can see and retrace what they drilled into most recently.

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
