# `seuss-hs` Session Additions

This file preserves the README details added or changed during the current editing session after restoring `README.md` to its earlier state.

## Additional command coverage

- `lsp` runs a minimal stdio language server with diagnostics, hover, and keyword completion.

## Importer additions from this session

- CSV import now accepts header aliases like `id`, `entity_type`, `lane`, `track`, `from`, and `to`.
- CSV entity imports now synthesize timeline declarations, sanitize generated identifiers, and preserve booleans, numbers, and ISO dates as typed literals.
- GEDCOM import now keeps family structure by emitting `spouse` and `parent_of` relationships in addition to person entities.
- JSON-LD import now turns `@id` references inside object properties and arrays into Seuss relationships instead of flattening them into opaque fields.

## Language additions from this session

- explicit `return` statements now parse and short-circuit function bodies, including returns from inside loop bodies.

## TUI additions from this session

- `Enter` follows the current selection: timelines jump into their entities, entities open neighborhood relationships, and relationships jump back to entities.
- `s` and `g` jump from a selected relationship to its source or target entity.
- `:` now also supports commands like `clear-filters`, `follow`, `rel-source`, and `rel-target`.
- the inspector now keeps a short recent-selection trail so users can see and retrace what they drilled into most recently.
