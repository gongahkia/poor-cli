[![](https://img.shields.io/badge/seuss_0.1.0-passing-green)](https://github.com/gongahkia/seuss/releases/tag/v0.1.0)
![](https://github.com/gongahkia/seuss/actions/workflows/ci.yml/badge.svg)
![](https://github.com/gongahkia/seuss/actions/workflows/release.yml/badge.svg)

# `Seuss`

Seuss is a [domain-specific language](https://en.wikipedia.org/wiki/Domain-specific_language) for modeling [timelines](https://en.wikipedia.org/wiki/Timeline) and their [evolutions](https://en.wikipedia.org/wiki/Temporal_paradox).

<div align="center">
    <img src="./asset/logo/seuss.jpg" width="50%">
</div>

## Stack

* *Scripting*: [Rust](https://rust-lang.org/), [pest](https://pest.rs/), [clap](https://docs.rs/clap), [thiserror](https://docs.rs/thiserror)
* *TUI*: [ratatui](https://ratatui.rs/), [crossterm](https://docs.rs/crossterm) 
* *Export Format*: [svg](https://docs.rs/svg), [resvg](https://docs.rs/resvg), [printpdf](https://docs.rs/printpdf) 
* *Date/Time*: [chrono](https://docs.rs/chrono) 
* *Serialization*: [serde](https://serde.rs/), [serde_json](https://docs.rs/serde_json), [toml](https://docs.rs/toml), [uuid](https://docs.rs/uuid)
* *CI/CD*: [GitHub Actions](https://github.com/features/actions)

## Screenshots

<div align="center">
    <img src="./asset/reference/1.png" width="32%">
    <img src="./asset/reference/6.png" width="32%">
    <img src="./asset/reference/3.png" width="32%">
</div>

<div align="center">
    <img src="./asset/reference/4.png" width="32%">
    <img src="./asset/reference/2.png" width="32%">
    <img src="./asset/reference/5.png" width="32%">
</div>

## Usage

### Installation

```console
$ git clone https://github.com/gongahkia/seuss && cd seuss
$ cargo build --release
```

The binary is at `./target/release/seuss`. Optionally copy it to your PATH:

```console
$ cp ./target/release/seuss /usr/local/bin/
```

### Quick start

```console
$ seuss check examples/ww2.seuss          # validate a file
$ seuss run examples/ww2.seuss            # open interactive TUI
$ seuss export examples/ww2.seuss -f svg -o timeline.svg   # export SVG
$ seuss repl                              # start interactive REPL
```

### Commands

| Command | Description |
|---------|-------------|
| `seuss run <file>` | Parse and visualize a `.seuss` file in the interactive terminal TUI |
| `seuss export <file> -f svg -o out.svg` | Export timeline as SVG |
| `seuss export <file> -f png -o out.png` | Export timeline as PNG (configurable `--dpi`, default 150) |
| `seuss export <file> -f pdf -o out.pdf` | Export timeline as vector PDF |
| `seuss check <file>` | Validate a `.seuss` file without rendering |
| `seuss diff <file1> <file2>` | Colorized diff of two `.seuss` files (timelines, entities, relationships) |
| `seuss import <file> --from csv` | Import from CSV, GEDCOM, or JSON-LD into `.seuss` format |
| `seuss repl` | Interactive REPL with file discovery, `:load`, `:world`, `:entities`, `:rels` |

### Global flags

| Flag | Description |
|------|-------------|
| `--verbose` | Enable debug logging |
| `--config <path>` | Path to a TOML config file for default export settings |
| `--theme <name>` | Theme: `dark` (default), `light`, or path to a custom TOML theme |

### Export options

```console
$ seuss export examples/ww2.seuss -f svg -o ww2.svg
$ seuss export examples/ww2.seuss -f png -o ww2.png --dpi 300
$ seuss export examples/ww2.seuss -f pdf -o ww2.pdf
$ seuss export examples/ww2.seuss -f svg --width 1920 --height 1080
```

### REPL

The REPL auto-discovers `.seuss` files in the current directory on startup.

```console
$ seuss repl
Seuss REPL v0.1.0 — type declarations, then :world to inspect, :quit to exit
  Found 2 .seuss file(s):
    [1] examples/lotr.seuss
    [2] examples/ww2.seuss
  Use :load <number> or :load <path> to load a file

seuss> :load 2
✓ Loaded examples/ww2.seuss (4 timelines, 26 entities, 29 relationships)
seuss> :entities
seuss> :rels
seuss> :validate
seuss> :quit
```

| Command | Description |
|---------|-------------|
| `:load <n>` or `:load <path>` | Load a `.seuss` file by index or path |
| `:files` / `:f` | Re-scan and list available `.seuss` files |
| `:world` / `:w` | Show all timelines, entities, and relationships |
| `:entities` / `:e` | Table of all entities with type, timeline, and time range |
| `:rels` / `:r` | Table of all relationships with source, label, target, directionality |
| `:validate` / `:v` | Run structural validation and report errors/warnings |
| `:timeline` / `:t` | ASCII mini-timeline visualization |
| `:quit` / `:q` | Exit the REPL |

You can also type raw Seuss declarations directly into the REPL to build a world interactively.

## TUI

The `seuss run` command opens a full-screen interactive terminal interface for exploring timelines.

### Navigation

| Key | Action |
|-----|--------|
| `h` / `←` | Pan left |
| `l` / `→` | Pan right |
| `k` / `↑` | Pan up |
| `j` / `↓` | Pan down |
| `+` / `=` | Zoom in |
| `-` | Zoom out |
| `q` | Quit |

### Entity interaction

| Key | Action |
|-----|--------|
| `Tab` | Cycle selection through entities |
| `Enter` | Drill down into selected entity |
| `Backspace` | Drill up (navigate back) |
| `Esc` | Deselect current entity |

### Modes

| Key | Action |
|-----|--------|
| `/` | Enter search mode — type to filter entities, `Enter` to jump, `Esc` to cancel |
| `f` | Enter filter mode — press `t` to toggle entity type filters |
| `?` | Toggle help overlay |
| `B` | Branch navigation — press `0`–`9` to focus on a timeline |
| `C` | Compare mode — select two timelines to view a side-by-side diff |
| `Ctrl+p` | Open command palette |

### Time controls

| Key | Action |
|-----|--------|
| `[` | Step time cursor backward |
| `]` | Step time cursor forward |
| `Space` | Play/pause time scrubber |

### Bookmarks

| Key | Action |
|-----|--------|
| `Ctrl+b` | Save current viewport as a bookmark |
| `1`–`9` | Jump to a saved bookmark |

### Undo/Redo

| Key | Action |
|-----|--------|
| `Ctrl+z` | Undo last navigation action |
| `Ctrl+y` | Redo |

### Layer cycling

| Key | Action |
|-----|--------|
| `v` | Cycle through display layers (All → Entities → Relationships → Events) |

## Syntax

Learn more about `Seuss`' syntax at [`SYNTAX.md`](./docs/SYNTAX.md).

Alternatively, refer to examples which live at [`./examples`](./examples/).

## Architecture

<div align="center">
    <img src="./asset/reference/architecture.png">
</div>