# Seuss Syntax Reference

Syntax reference for the current Haskell implementation of Seuss.

For more examples, see the [`examples/`](../examples/) directory.

## Table of Contents

- [Comments](#comments)
- [Literals](#literals)
- [Identifiers](#identifiers)
- [Timelines](#timelines)
- [Entities](#entities)
- [Relationships](#relationships)
- [Custom Types](#custom-types)
- [Variables](#variables)
- [Functions](#functions)
- [Control Flow](#control-flow)
- [Operators](#operators)
- [Imports](#imports)
- [Field Access](#field-access)
- [Lists](#lists)
- [Complete Example](#complete-example)

---

## Comments

Seuss supports single-line and block comments.

```seuss
// This is a single-line comment

/* This is a
   block comment */
```

---

## Literals

The current parser accepts integers, strings, booleans, and ISO dates.

### Integers

```seuss
42
0
1000
```

### Strings

Strings are double-quoted and use Megaparsec character escapes.

```seuss
"hello world"
"line one\nline two"
"a \"quoted\" word"
```

### Booleans

```seuss
true
false
```

### Dates

Dates follow the `YYYY-MM-DD` format.

```seuss
1939-09-01
2024-12-25
```

---

## Identifiers

Identifiers start with a letter or underscore, followed by letters, digits, or underscores.

```seuss
my_entity
timeline_1
_private
warPhase2
```

---

## Timelines

A timeline defines a named temporal span.

```seuss
timeline main {
    kind: linear,
    start: 1939-09-01,
    end: 1945-09-02,
}
```

### Timeline kinds

| Kind | Description |
|------|-------------|
| `linear` | A single sequential timeline |
| `branch` | A timeline that diverges from another |
| `parallel` | A concurrent timeline |
| `loop` | A repeating timeline |

### Timeline fields

| Field | Required | Description |
|-------|----------|-------------|
| `kind` | No | One of `linear`, `branch`, `parallel`, `loop`; defaults to `linear` |
| `start` | No | Start date or integer time point; defaults to `0` |
| `end` | No | End date or integer time point; defaults to `100` |
| `parent` | No | Parent timeline name |
| `fork_from` | No | Fork point written as `timeline_name @ expr` |
| `merge_into` | No | Merge point written as `timeline_name @ expr` |
| `loop_count` | No | Loop iteration count |

### Branching and merging

```seuss
timeline main {
    kind: linear,
    start: 2000-01-01,
    end: 2020-12-31,
}

timeline alternate {
    kind: branch,
    start: 2010-06-15,
    end: 2020-12-31,
    fork_from: main @ 2010-06-15,
    merge_into: main @ 2018-01-01,
}
```

### Looping timelines

```seuss
timeline cycle {
    kind: loop,
    start: 2000-01-01,
    end: 2000-12-31,
    loop_count: 4,
}
```

---

## Entities

Entities are attached to one or more timelines through `appears_on`.

```seuss
entity frodo : character {
    age: 50,
    appears_on: main @ 2968-09-22..3019-09-29,
}
```

### Syntax

```text
entity <name> : <type>? {
    <field>: <value>,
    appears_on: <timeline> @ <start>..<end>,
}
```

- The `: <type>` clause is optional; omitted types default to `entity` at evaluation time.
- `appears_on` can be repeated to give an entity multiple appearances.
- Custom fields are stored as evaluated values in the entity record.

### Built-in types

These type labels are always available without a `type` declaration:

| Type | Typical use |
|------|-------------|
| `entity` | Generic default |
| `event` | Event entities |
| `person` | People |
| `place` | Places |
| `object` | Objects |
| `group` | Groups |
| `character` | Narrative characters |
| `artifact` | Named objects with story significance |
| `location` | Places with explicit timeline appearances |
| `faction` | Group or organization entities |

---

## Relationships

Relationships are always written as directed edges in the current parser.

### Directed and labeled

```seuss
rel churchill -["allied_with"]-> roosevelt;
```

### Directed and unlabeled

```seuss
rel cause --> effect;
```

### Temporal scope

```seuss
rel traveler -["meets"]-> guide @ 2001-01-01..2001-01-31;
```

---

## Custom Types

Custom types declare fields and optional metadata.

```seuss
type leader {
    nation: string,
    rank: string,
    @icon: "crown",
}
```

### Inheritance

```seuss
type battle : event {
    theater: string,
    outcome: string,
}
```

### Metadata

`@` fields are stored as type metadata and can be read by the evaluator or renderers.

```seuss
type faction {
    name: string,
    @color: "#2f6fed",
    @shape: "diamond",
}
```

---

## Variables

`let` bindings support optional `mut` and optional type annotations.

```seuss
let war_duration = 6;
let mut counter = 0;
let name: string = "Frodo";
counter = counter + 1;
```

---

## Functions

Functions are declared with `fn`, typed parameters, and an optional return type.

```seuss
fn summarize(count: int) -> string {
    if count > 1 {
        return "multiple";
    }
    return "single";
}
```

Closures are also supported:

```seuss
let labeler = |name: string| name;
```

---

## Control Flow

### Conditionals

```seuss
if true {
    let branch = "then";
} else if false {
    let branch = "else-if";
} else {
    let branch = "else";
}
```

### Match

Each arm body is a block.

```seuss
match status {
    "active" => {
        let running = true;
    },
    state => {
        let seen = state;
    },
    _ => {
        let running = false;
    },
}
```

### For loops

`for` accepts ranges, list literals, or general expressions.

```seuss
for i in 1..3 {
    let phase = i;
}

for label in ["one", "two"] {
    let current = label;
}
```

### Repeat loops

```seuss
repeat 3 {
    let tick = true;
}
```

### While loops

```seuss
let mut counter = 0;

while counter < 3 {
    counter = counter + 1;
}
```

---

## Operators

The current parser supports the following operators:

| Category | Operators |
|----------|-----------|
| Arithmetic | `+`, `-` |
| Comparison | `>`, `<`, `>=`, `<=`, `==`, `!=` |
| Boolean | `&&`, `||` |
| Range | `..` |

---

## Imports

Imports are written as file paths and are expanded by the CLI loader before parsing.

```seuss
import "shared/common.seuss";
```

---

## Field Access

Field access and indexing are both supported in expressions.

```seuss
entity frodo : character {
    age: 50,
    appears_on: main @ 2968-09-22..3019-09-29,
}

let age_value = frodo.age;
let first_name = ["frodo", "sam"][0];
```

---

## Lists

List literals and ranges are first-class expressions.

```seuss
let values = [1, 2, 3];
let days = 1..3;
```

---

## Complete Example

```seuss
type leader {
    nation: string,
}

timeline main {
    kind: linear,
    start: 1939-09-01,
    end: 1945-09-02,
}

entity churchill : leader {
    nation: "United Kingdom",
    appears_on: main @ 1939-09-03..1945-05-08,
}

entity roosevelt : leader {
    nation: "United States",
    appears_on: main @ 1941-12-11..1945-04-12,
}

rel churchill -["allied_with"]-> roosevelt;

let war_duration = 6;

if war_duration > 5 {
    let long_war = true;
}
```

Relationships can be scoped to a time range.

```seuss
rel frodo -["carries"]-> ring @ 3018-04-01..3019-03-25;
```

### Arrow reference

| Arrow | Directed | Labeled |
|-------|----------|---------|
| `-["label"]->` | Yes | Yes |
| `-["label"]-` | No | Yes |
| `-->` | Yes | No |
| `--` | No | No |

---

## Temporal Expressions

Seuss has rich temporal expression support for specifying when things happen.

### Date literals

```seuss
1945-08-06
```

### Fuzzy dates

Prefix a date with `~` to indicate an approximate date.

```seuss
~1945-08-06
```

### Time ranges

Two dates or expressions joined by `..`.

```seuss
1939-09-01..1945-05-08
```

### Relative time

A duration before or after a named reference point.

```seuss
5years after war_start
3months before d_day
```

### Era references

Reference a specific point within a timeline's named eras using `::` syntax.

```seuss
main::medieval::start
european_theater::blitz::end
```

---

## Custom Types

Define reusable types with typed fields and optional inheritance.

### Basic type

```seuss
type leader {
    nation: string,
    rank: string,
}
```

### Type with inheritance

A child type inherits all fields from its parent and can add or override fields.

```seuss
type battle : event {
    theater: string,
    outcome: string,
}
```

### Field types

| Type | Description |
|------|-------------|
| `int` | Integer number |
| `float` | Floating point number |
| `string` | Text string |
| `bool` | Boolean (`true`/`false`) |
| `date` | Date value |
| Any other name | Entity reference to that type |

### Optional fields

Append `?` to mark a field as optional.

```seuss
type character {
    name: string,
    title: string?,
    age: int?,
}
```

### Meta-attributes (render hints)

Fields prefixed with `@` are render hints that control how entities of this type are displayed.

```seuss
type important_event {
    @color: "#ff4444",
    @shape: "diamond",
    @icon: "star",
    description: string,
}
```

| Meta-attribute | Effect |
|---------------|--------|
| `@color` | Fill color in SVG/TUI rendering |
| `@shape` | Shape: `rect`, `circle`, or `diamond` |
| `@icon` | Icon label rendered alongside the entity |
| `@label_format` | Custom label format string |

---

## Variables

### Let bindings

```seuss
let war_duration = 6;
let name = "World War II";
let is_global = true;
let start_date = 1939-09-01;
```

### Mutable variables

```seuss
let mut counter = 0;
counter = counter + 1;
```

### Type annotations (optional)

```seuss
let count: int = 42;
let label: string = "test";
```

---

## Functions

### Function declarations

```seuss
fn greet(name: string) {
    let msg = "hello";
}

fn add(a: int, b: int) -> int {
    a + b
}
```

### Function calls

```seuss
greet("world");
let sum = add(1, 2);
```

### Closures

```seuss
let double = |x: int| x * 2;
```

---

## Control Flow

### If / else if / else

```seuss
if count > 10 {
    let big = true;
} else if count > 5 {
    let medium = true;
} else {
    let small = true;
}
```

### Match

```seuss
match status {
    "active" => { let running = true; },
    "stopped" => { let running = false; },
    _ => { let running = false; },
}
```

The `_` pattern is a wildcard that matches anything.

### For loop

Iterate over a list.

```seuss
for i in [1, 2, 3] {
    let x = i;
}
```

### While loop

```seuss
let mut n = 0;
while n < 5 {
    n = n + 1;
}
```

### Repeat loop

Execute a block a fixed number of times.

```seuss
repeat 3 {
    let tick = true;
}
```

---

## Operators

### Arithmetic

| Operator | Description |
|----------|-------------|
| `+` | Addition |
| `-` | Subtraction |
| `*` | Multiplication |
| `/` | Division |

### Comparison

| Operator | Description |
|----------|-------------|
| `==` | Equal |
| `!=` | Not equal |
| `<` | Less than |
| `>` | Greater than |
| `<=` | Less than or equal |
| `>=` | Greater than or equal |

### Logical

| Operator | Description |
|----------|-------------|
| `&&` | Logical AND |
| `\|\|` | Logical OR |
| `!` | Logical NOT (unary) |

### Range

```seuss
1939-09-01..1945-09-02
```

The `..` operator creates a time range between two expressions.

### Unary

| Operator | Description |
|----------|-------------|
| `-` | Numeric negation |
| `!` | Logical negation |

---

## Imports

Import other `.seuss` files.

```seuss
import "types/common.seuss";
import "data/characters.seuss";
```

---

## Field Access

Access fields on entities and timelines using dot notation.

```seuss
frodo.name
frodo.age
main.kind
```

If a field is not set directly on an entity, Seuss walks up the type inheritance chain to find inherited default values.

---

## Lists

Create lists with square brackets.

```seuss
let numbers = [1, 2, 3, 4, 5];
let names = ["alice", "bob", "charlie"];
```

---

## Complete Example

```seuss
// Define custom types
type leader {
    nation: string,
    rank: string,
}

type battle : event {
    theater: string,
    outcome: string,
}

// Create timelines
timeline european_theater {
    kind: linear,
    start: 1939-09-01,
    end: 1945-05-08,
}

timeline pacific_theater {
    kind: linear,
    start: 1941-12-07,
    end: 1945-09-02,
}

// Create entities
entity churchill : leader {
    nation: "United Kingdom",
    rank: "Prime Minister",
    appears_on: european_theater @ 1939-09-03..1945-05-08,
}

entity d_day : battle {
    theater: "Western Front",
    outcome: "Allied victory",
    appears_on: european_theater @ 1944-06-06..1944-08-25,
}

// Create relationships
rel churchill -["commanded"]-> d_day;

// Use variables and logic
let total_battles = 12;

if total_battles > 10 {
    let large_conflict = true;
}
```
