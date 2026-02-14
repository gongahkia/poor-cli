[![](https://img.shields.io/badge/seuss_1.0.0-passing-light_green)](https://github.com/gongahkia/seuss/releases/tag/1.0.0)
[![](https://img.shields.io/badge/seuss_2.0.0-passing-green)](https://github.com/gongahkia/seuss/releases/tag/2.0.0)
[![](https://img.shields.io/badge/seuss_3.0.0-passing-blue)](https://github.com/gongahkia/seuss)

# `Seuss`

A DSL for modeling and visualizing temporal narratives — timelines, entities, relationships, and their evolution over time.

Built in Rust with a PEG parser, evaluator, TUI (ratatui), and SVG renderer.

<div align="center">
    <img src="https://images.artbrokerage.com/artthumb/geisel_162877_9/632x632/Dr_Seuss_Oh_the_Stuff_You_Will_Learn_CP.jpg" width="50%">
</div>

## Quick Start

```console
$ cargo build --release
$ ./target/release/seuss check examples/lotr.seuss
$ ./target/release/seuss run examples/lotr.seuss
$ ./target/release/seuss export examples/lotr.seuss --format svg --output timeline.svg
```

## Example `.seuss` File

```
timeline main {
    kind: linear,
    start: 2941-01-01,
    end: 3019-12-31,
}

entity frodo : character {
    age: 50,
    appears_on: main @ 2968-09-22..3019-09-29,
}

entity gandalf : character {
    role: "wizard",
    appears_on: main @ 2941-01-01..3019-12-31,
}

rel gandalf -["guides"]-> frodo;
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `seuss run <file.seuss>` | Parse and visualize in terminal TUI |
| `seuss export <file.seuss> --format svg` | Export as SVG |
| `seuss check <file.seuss>` | Validate without rendering |

## TUI Keybindings

| Key | Action |
|-----|--------|
| `h/j/k/l` or arrows | Pan viewport |
| `+/-` | Zoom in/out |
| `Tab` | Cycle entity selection |
| `Enter` | Focus on selected entity |
| `/` | Search entities |
| `?` | Toggle help |
| `q` | Quit |

## Architecture

- **lang/** — PEG grammar (pest), parser, AST
- **model/** — Timeline, Entity, Relationship, World data structures
- **eval/** — Expression evaluator, variable environment, builtins
- **layout/** — Time axis, swim lanes, viewport model
- **tui/** — ratatui terminal interface
- **render/** — SVG output with theming
- **cli/** — clap command definitions
