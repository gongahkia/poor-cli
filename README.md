[![](https://img.shields.io/badge/seuss_1.0.0-passing-green)](https://github.com/gongahkia/seuss/releases/tag/v1.0.0)
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

The below instructions are for running `Seuss` locally.

1. First execute the below command to clone `Seuss` on your local machine.

```console
$ git clone https://github.com/gongahkia/seuss && cd seuss
$ cargo build --release # built binary lives at ./target/release/seuss
$ cp ./target/release/seuss /usr/local/bin/ # optionally copy the binary to your PATH
```

2. Next, run any of the below commands *(and flags)* to interact with `Seuss` and its [TUI](#tui-commands).

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

### Flags

| Flag | Description |
|------|-------------|
| `--verbose` | Enable debug logging |
| `--config <path>` | Path to a TOML config file for default export settings |
| `--theme <name>` | Theme: `dark` (default), `light`, or path to a custom TOML theme |

3. Additionally, `Seuss` provides export options to the below file formats.

```console
$ seuss export examples/ww2.seuss -f svg -o ww2.svg
$ seuss export examples/ww2.seuss -f png -o ww2.png --dpi 300
$ seuss export examples/ww2.seuss -f pdf -o ww2.pdf
$ seuss export examples/ww2.seuss -f svg --width 1920 --height 1080
```

4. Finally, interact with `Seuss`' REPL via the below, or type raw `Seuss` declarations to interactively build a timeline.

### REPL commands

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

### TUI commands

The `seuss run` command opens a full-screen interactive terminal interface for exploring timelines.

#### Navigation

| Key | Action |
|-----|--------|
| `h` / `←` | Pan left |
| `l` / `→` | Pan right |
| `k` / `↑` | Pan up |
| `j` / `↓` | Pan down |
| `+` / `=` | Zoom in |
| `-` | Zoom out |
| `q` | Quit |

#### Entity interaction

| Key | Action |
|-----|--------|
| `Tab` | Cycle selection through entities |
| `Enter` | Drill down into selected entity |
| `Backspace` | Drill up (navigate back) |
| `Esc` | Deselect current entity |

#### Modes

| Key | Action |
|-----|--------|
| `/` | Enter search mode — type to filter entities, `Enter` to jump, `Esc` to cancel |
| `f` | Enter filter mode — press `t` to toggle entity type filters |
| `?` | Toggle help overlay |
| `B` | Branch navigation — press `0`–`9` to focus on a timeline |
| `C` | Compare mode — select two timelines to view a side-by-side diff |
| `Ctrl+p` | Open command palette |

#### Time controls

| Key | Action |
|-----|--------|
| `[` | Step time cursor backward |
| `]` | Step time cursor forward |
| `Space` | Play/pause time scrubber |

#### Bookmarks

| Key | Action |
|-----|--------|
| `Ctrl+b` | Save current viewport as a bookmark |
| `1`–`9` | Jump to a saved bookmark |

#### Undo/Redo

| Key | Action |
|-----|--------|
| `Ctrl+z` | Undo last navigation action |
| `Ctrl+y` | Redo |

#### Layer cycling

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