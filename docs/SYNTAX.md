# Seuss Syntax Reference

Complete syntax reference for the Seuss DSL [v1.0.0](https://github.com/gongahkia/seuss/releases/tag/v0.1.0). 

For more examples, see the [`examples/`](../examples/) directory.

## Table of Contents

- [Comments](#comments)
- [Literals](#literals)
- [Identifiers](#identifiers)
- [Timelines](#timelines)
- [Entities](#entities)
- [Relationships](#relationships)
- [Temporal Expressions](#temporal-expressions)
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

### Integers

```seuss
42
0
1000
```

### Floats

```seuss
3.14
0.5
100.0
```

### Strings

Strings are double-quoted. Escape sequences are supported.

```seuss
"hello world"
"line one\nline two"
"a \"quoted\" word"
"curly \{braces\}"
```

Supported escape sequences: `\n`, `\t`, `\r`, `\\`, `\"`, `\{`, `\}`.

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

### Durations

A number followed by a time unit.

```seuss
5days
3months
10years
2weeks
1day
1month
1year
1week
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

A timeline defines a temporal span in which entities can appear. Every Seuss program needs at least one timeline.

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
| `parallel` | A timeline that runs alongside others |
| `loop` | A repeating timeline |

### Timeline fields

| Field | Required | Description |
|-------|----------|-------------|
| `kind` | Yes | One of `linear`, `branch`, `parallel`, `loop` |
| `start` | Yes | Start date or expression |
| `end` | Yes | End date or expression |
| `parent` | No | Parent timeline name (for branches) |
| `fork_from` | No | Fork point: `timeline_name @ date` |
| `merge_into` | No | Merge point: `timeline_name @ date` |
| `loop_count` | No | Number of repetitions (for `loop` kind) |

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

Entities are the things that exist on timelines — people, events, objects, places, or any custom type.

```seuss
entity frodo : character {
    age: 50,
    appears_on: main @ 2968-09-22..3019-09-29,
}
```

### Syntax

```
entity <name> : <type>? {
    <field>: <value>,
    appears_on: <timeline> @ <start>..<end>,
}
```

- The `: <type>` is optional. If omitted, the entity defaults to the built-in `entity` type.
- `appears_on` places the entity on a timeline for a given time range.
- An entity can have any number of custom fields.

### Built-in types

These type labels are always available without a `type` declaration:

| Type | Typical use |
|------|-------------|
| `entity` | Generic (default) |
| `event` | A point or span event |
| `person` | A human individual |
| `place` | A location |
| `object` | A physical thing |
| `group` | A collection of entities |

### Multiple timeline appearances

An entity can appear on multiple timelines by repeating the `appears_on` field.

```seuss
entity traveler : person {
    appears_on: timeline_a @ 2000-01-01..2005-12-31,
    appears_on: timeline_b @ 2003-06-01..2010-12-31,
}
```

---

## Relationships

Relationships connect two entities with an optional label and directionality.

### Directed and labeled (most common)

```seuss
rel churchill -["allied with"]-> roosevelt;
```

### Undirected and labeled

```seuss
rel alice -["siblings"]- bob;
```

### Directed, unlabeled

```seuss
rel cause --> effect;
```

### Undirected, unlabeled

```seuss
rel node_a -- node_b;
```

### Temporal scope

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