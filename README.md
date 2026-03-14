[![](https://img.shields.io/badge/seuss_1.0.0-passing-light_green)](https://github.com/gongahkia/seuss/releases/tag/1.0.0)
[![](https://img.shields.io/badge/seuss_2.0.0-passing-green)](https://github.com/gongahkia/seuss/releases/tag/2.0.0)
![](https://github.com/gongahkia/seuss/actions/workflows/ci.yml/badge.svg)
![](https://github.com/gongahkia/seuss/actions/workflows/release.yml/badge.svg)

# `Seuss`

Seuss is a [domain-specific language](https://en.wikipedia.org/wiki/Domain-specific_language) for modeling [timelines](https://en.wikipedia.org/wiki/Timeline) and their [evolutions](https://en.wikipedia.org/wiki/Temporal_paradox).

<div align="center">
    <img src="./asset/logo/seuss.jpg" width="50%">
</div>

## Stack

* *Language & Parsing*: [Haskell](https://www.haskell.org/), [megaparsec](https://hackage.haskell.org/package/megaparsec), [optparse-applicative](https://hackage.haskell.org/package/optparse-applicative), [text](https://hackage.haskell.org/package/text)
* *TUI*: [brick](https://hackage.haskell.org/package/brick), [vty](https://hackage.haskell.org/package/vty)
* *Export Format*: [SVG](https://www.w3.org/Graphics/SVG/), [aeson](https://hackage.haskell.org/package/aeson), [tomland](https://hackage.haskell.org/package/tomland)
* *Data & Utilities*: [containers](https://hackage.haskell.org/package/containers), [bytestring](https://hackage.haskell.org/package/bytestring), [filepath](https://hackage.haskell.org/package/filepath), [time](https://hackage.haskell.org/package/time)
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

1. First execute the below command to clone the current Haskell implementation of `Seuss` onto your local machine.

```console
$ git clone https://github.com/gongahkia/seuss && cd seuss
$ cabal update
$ cabal build all
$ cabal run seuss -- --help
$ cabal install exe:seuss --installdir="$HOME/.local/bin" --overwrite-policy=always
```

2. Next run any of the below [commands and flags](#commands-and-flags) to interact with `Seuss` and its [TUI](#tui-commands).

3. `Seuss`' current implementation additionally supports SVG export via the below commands.

```console
$ seuss export examples/ww2.seuss -f svg -o ww2.svg
$ seuss export examples/lotr.seuss -f svg -o lotr.svg --width 1920 --height 1080
$ cabal run seuss -- export examples/ww2.seuss -f svg -o ww2.svg
$ cabal run seuss -- --theme light export examples/lotr.seuss -f svg -o lotr.svg
```

4. Finally, interact with `Seuss`' [REPL](#repl-commands) or type raw `Seuss` declarations to interactively build a timeline.

## Commands

### Commands and flags

| Command | Description |
|---------|-------------|
| `seuss run <file>` | Parse a `.seuss` file, validate it, and open the Brick-based terminal explorer |
| `seuss export <file> -f svg -o out.svg` | Export a `.seuss` file as SVG |
| `seuss check <file>` | Parse and validate a `.seuss` file without opening the TUI |
| `seuss diff <file1> <file2>` | Render a semantic diff of timelines, entities, and relationships |
| `seuss import <file> --from csv` | Import CSV, GEDCOM, or JSON-LD data into `.seuss` source |
| `seuss repl` | Start the interactive REPL with `:load`, `:world`, `:entities`, and `:rels` |
| `seuss lsp` | Run the stdio language server for completions, hover, and diagnostics |

| Flag | Description |
|------|-------------|
| `--verbose` | Print extra startup and command execution details |
| `--config <path>` | Path to a TOML config file for export defaults and theme settings |
| `--theme <name>` | Theme: `dark`, `light`, or a path to a custom TOML theme |

### REPL commands

| Command | Description |
|---------|-------------|
| `:load <n>` or `:load <path>` | Load a `.seuss` file by index or path |
| `:files` / `:f` | Re-scan and list available `.seuss` files |
| `:world` / `:w` | Show summary counts for timelines, entities, relationships, and types |
| `:entities` / `:e` | Print each entity with its type and appearance count |
| `:rels` / `:r` | Print each relationship in semantic edge form |
| `:validate` / `:v` | Run structural validation and print diagnostics |
| `:timeline` / `:t` | Render a text timeline grouped by timeline name |
| `:quit` / `:q` | Exit the REPL |

### TUI commands

#### Navigation

| Key | Action |
|-----|--------|
| `Tab` | Cycle the active pane (Timelines → Entities → Relationships → Inspector) |
| `k` / `↑` | Move the selection up in the active pane |
| `j` / `↓` | Move the selection down in the active pane |
| `Enter` | Follow the current selection into the next relevant pane |
| `q` | Quit |

#### Entity interaction

| Key | Action |
|-----|--------|
| `Enter` | Follow the selected timeline, entity, or relationship |
| `t` | Cycle the entity-type filter |
| `n` | Toggle neighborhood-only relationship mode |
| `s` | Jump from the selected relationship to its source entity |
| `g` | Jump from the selected relationship to its target entity |

#### Modes

| Key | Action |
|-----|--------|
| `/` | Enter search mode to filter visible entities |
| `:` | Open the command palette (`help`, `compare`, `bookmark`, `clear-search`, `clear-filters`) |
| `?` | Toggle help overlay |
| `c` | Cycle the timeline used for comparison in the inspector |
| `Esc` | Exit search or command mode |

#### Time controls

| Key | Action |
|-----|--------|
| `[` | Move the scrubber backward by one unit |
| `]` | Move the scrubber forward by one unit |
| `{` | Move the scrubber to the selected timeline start |
| `}` | Move the scrubber to the selected timeline end |

#### Bookmarks

| Key | Action |
|-----|--------|
| `b` | Save the current entity to the next bookmark slot |
| `1`–`9` | Jump to a saved bookmark |

#### Undo/Redo

| Key | Action |
|-----|--------|
| `u` | Undo the last selection, filter, or scrubber change |
| `y` | Redo |

#### Layer cycling

| Key | Action |
|-----|--------|
| `t` | Cycle through entity-type filters |
| `n` | Toggle relationship neighborhood filtering |

## Syntax

Learn more about `Seuss`' syntax at [`SYNTAX.md`](./docs/SYNTAX.md).

Alternatively, refer to examples which live at [`./examples`](./examples/).

## Architecture

<div align="center">
    <img src="./asset/reference/architecture.png">
</div>
