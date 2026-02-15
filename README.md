[![](https://img.shields.io/badge/seuss_1.0.0-passing-green)](https://github.com/gongahkia/seuss/releases/tag/1.0.0)
![](https://github.com/gongahkia/seuss/actions/workflows/ci.yml/badge.svg)
![](https://github.com/gongahkia/seuss/actions/workflows/release.yml/badge.svg)

# `Seuss`

[DSL](https://en.wikipedia.org/wiki/Domain-specific_language) for modeling and visualizing temporal narratives — timelines, entities, relationships, and their evolution over time.

Built in Rust with a PEG parser, evaluator, TUI (ratatui), and SVG renderer.

<div align="center">
    <img src="https://images.artbrokerage.com/artthumb/geisel_162877_9/632x632/Dr_Seuss_Oh_the_Stuff_You_Will_Learn_CP.jpg" width="50%">
</div>

## Stack

...

## Usage

...

```console
$ cargo build --release
$ ./target/release/seuss check examples/lotr.seuss
$ ./target/release/seuss run examples/lotr.seuss
$ ./target/release/seuss export examples/lotr.seuss --format svg --output timeline.svg
```

### CLI Commands

| Command | Description |
|---------|-------------|
| `seuss run <file.seuss>` | Parse and visualize in terminal TUI |
| `seuss export <file.seuss> --format svg` | Export as SVG |
| `seuss check <file.seuss>` | Validate without rendering |

### TUI Keybindings

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

...

## Reference

...
