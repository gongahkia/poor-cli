# Seuss Syntax Reference

This document describes the syntax and runtime behavior implemented by the current Haskell codebase. It does not describe planned or aspirational features.

For examples, see [`examples/`](../examples/).

## Lexical Rules

### Comments

```seuss
// line comment

/* block
   comment */
```

### Identifiers

Identifiers start with a letter or underscore, followed by letters, digits, or underscores.

```seuss
main
timeline_1
_private
warPhase2
```

### Literals

Supported literals:

- integers
- double-quoted strings
- booleans
- ISO dates in `YYYY-MM-DD` form

```seuss
42
"hello"
true
1945-05-08
```

Not currently supported:

- floating-point literals
- fuzzy dates such as `~1945-05-08`
- relative temporal phrases such as `5years after x`
- era references such as `main::era::start`

## Top-Level Statements

A Seuss file is a sequence of statements. The current parser accepts these top-level forms:

- `type`
- `timeline`
- `entity`
- `rel`
- `import`
- `let`
- `fn`
- `if`
- `match`
- `for`
- `repeat`
- `while`
- assignment statements
- expression statements
- `return` inside function bodies

`rel` and `import` require trailing semicolons. `let`, assignment, expression, and `return` statements accept an optional trailing semicolon.

## Timelines

Timelines define named temporal spans.

```seuss
timeline main {
    kind: linear,
    start: 1939-09-01,
    end: 1945-09-02,
}
```

Supported fields:

| Field | Type | Notes |
|---|---|---|
| `kind` | identifier | `linear`, `branch`, `parallel`, or `loop` |
| `start` | expr | date or integer at runtime |
| `end` | expr | date or integer at runtime |
| `parent` | identifier | validated after evaluation |
| `fork_from` | `timeline @ expr` | validated after evaluation |
| `merge_into` | `timeline @ expr` | validated after evaluation |
| `loop_count` | expr | must evaluate to an integer if present |

Defaults:

- omitted `kind` defaults to `linear`
- omitted `start` defaults to `0`
- omitted `end` defaults to `100`

Examples:

```seuss
timeline main {
    start: 1,
    end: 10,
}

timeline alternate {
    kind: branch,
    start: 3,
    end: 8,
    fork_from: main @ 3,
    merge_into: main @ 7,
}
```

Semantic rules:

- invalid explicit `kind` values are errors
- timeline bounds with `start > end` are errors
- missing `parent`, `fork_from`, and `merge_into` timeline references are errors

## Entities

Entities belong to zero or more timelines through `appears_on`.

```seuss
entity churchill : leader {
    nation: "United Kingdom",
    appears_on: main @ 1939-09-03..1945-05-08,
}
```

General form:

```text
entity <name> : <type>? {
    <field>: <expr>,
    appears_on: <timeline> @ <start>..<end>,
}
```

Notes:

- the type annotation is optional; omitted types become `entity`
- `appears_on` may appear multiple times
- non-`appears_on` fields are stored as evaluated values

Built-in entity type labels:

- `entity`
- `event`
- `person`
- `place`
- `object`
- `group`
- `character`
- `artifact`
- `location`
- `faction`

Semantic rules:

- references to missing timelines are errors
- appearance ranges with `start > end` are errors
- appearances outside timeline bounds are errors
- unknown custom entity types are warnings, not errors

## Relationships

Relationships are directed in the current parser.

Supported arrow forms:

- labeled: `-["label"]->`
- unlabeled: `-->`

Examples:

```seuss
rel churchill -["allied_with"]-> roosevelt;
rel cause --> effect;
rel traveler -["meets"]-> guide @ 2001-01-01..2001-01-31;
```

Semantic rules:

- relationship source and target entities must exist
- temporal scopes with `start > end` are errors

Not currently supported:

- undirected arrows such as `--` or `-["label"]-`

## Custom Types

Custom types declare reusable entity field schemas and optional metadata.

```seuss
type leader {
    nation: string,
    rank: string,
    @icon: "crown",
}
```

Inheritance is supported:

```seuss
type battle : event {
    theater: string,
}
```

Field syntax:

```text
field_name: type_name,
optional_field: type_name?,
@meta_name: <expr>,
```

Supported scalar/runtime type names in validation:

- `int`
- `string`
- `bool`
- `date`
- `list`
- `entity`
- `timeline`
- `closure`

Declared custom types may also be used as field types for entity references.

Semantic rules:

- inherited fields are included when validating entities
- non-optional declared fields are required
- declared field values are checked against their declared types
- type metadata is available through entity field access fallback

## Variables And Assignment

`let` supports optional `mut` and optional type annotations.

```seuss
let answer = 42;
let mut counter = 0;
let name: string = "Frodo";
counter = counter + 1;
```

Semantic rules:

- unresolved identifiers are errors
- assignment to an undefined name is an error
- assignment to a non-`mut` binding is an error
- type annotations on `let` bindings are enforced at evaluation time

## Functions And Closures

Functions use typed parameters and an optional return type.

```seuss
fn summarize(count: int) -> string {
    if count > 1 {
        return "multiple";
    }
    return "single";
}
```

Closures are expression-bodied:

```seuss
let labeler = |name: string| name;
```

Built-in callable names:

- `len`
- `before`
- `after`
- `type_of`

Current call semantics:

- named functions are callable
- closure values are callable
- other values are not callable
- `return` is only valid inside function bodies

## Control Flow

### Conditionals

```seuss
if false {
    let branch = 0;
} else if true {
    let branch = 1;
} else {
    let branch = 2;
}
```

Conditions must evaluate to booleans.

### Match

Supported match patterns:

- literal values
- identifier bindings
- `_`

```seuss
match status {
    "active" => { let running = true; },
    state => { let seen = state; },
    _ => { let running = false; },
}
```

### For

`for` accepts:

- ranges
- list literals
- general expressions

```seuss
for i in 1..3 {
    let phase = i;
}

for label in ["one", "two"] {
    let current = label;
}
```

If the iterable expression evaluates to a list, the loop iterates that list. Otherwise the current evaluator treats the value as a single-item iteration.

### Repeat

```seuss
repeat 3 {
    let tick = true;
}
```

Repeat counts must evaluate to non-negative integers.

### While

```seuss
let mut counter = 0;

while counter < 3 {
    counter = counter + 1;
}
```

While conditions must evaluate to booleans. The evaluator also enforces a maximum iteration limit.

## Expressions

Supported expression forms:

- literals
- identifiers
- list literals
- ranges
- indexing
- field access
- function and closure calls
- closures
- binary expressions

Operator support:

| Category | Operators |
|---|---|
| arithmetic | `+`, `-` |
| comparison | `>`, `<`, `>=`, `<=`, `==`, `!=` |
| boolean | `&&`, `||` |
| range | `..` |

Precedence, highest to lowest:

1. postfix access and calls
2. `+`, `-`
3. comparisons
4. `&&`
5. `||`
6. `..`

Not currently supported:

- `*`
- `/`
- unary `!`

## Field Access And Indexing

Examples:

```seuss
let first = ["frodo", "sam"][0];
let kind_name = main.kind;
let nation = churchill.nation;
```

Timeline field access supports:

- `name`
- `kind`
- `start`
- `end`
- `parent`
- `loop_count`

Entity field access supports:

- `name`
- `type`
- declared entity fields
- inherited type metadata fallback

## Imports

Imports are string paths:

```seuss
import "shared/common.seuss";
```

The current CLI loader expands imports before parsing.

## Audit-Driven Semantics

The current implementation now enforces these rules explicitly:

- unresolved names fail instead of silently becoming strings
- `let mut` is enforced for reassignment
- explicit invalid timeline kinds fail instead of defaulting
- declared entity type requirements are validated
- diagnostics carry source locations through the parser, evaluator, validation, and LSP layers
