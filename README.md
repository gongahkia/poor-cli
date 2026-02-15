[![](https://img.shields.io/badge/seuss_1.0.0-passing-green)](https://github.com/gongahkia/seuss/releases/tag/1.0.0)
![](https://github.com/gongahkia/seuss/actions/workflows/ci.yml/badge.svg)
![](https://github.com/gongahkia/seuss/actions/workflows/release.yml/badge.svg)

# `Seuss`

Seuss is a [domain-specific language](https://en.wikipedia.org/wiki/Domain-specific_language) for modeling [timelines](https://en.wikipedia.org/wiki/Timeline) and their [evolutions](https://en.wikipedia.org/wiki/Temporal_paradox).

<div align="center">
    <img src="./asset/logo/seuss.jpg" width="50%">
</div>

## Stack

* *Scripting*: [Rust](https://rust-lang.org/), ...
* ...

## Screenshots



## Usage

The below instructions are for running `Seuss` locally.

1. First run the below to install `Seuss` on your local machine.

```console
$ git clone https://github.com/gongahkia/seuss && cd seuss
```

2. Then execute the below commands to use `Seuss`.

```console
$ cargo build --release
$ ./target/release/seuss check examples/lotr.seuss
$ ./target/release/seuss run examples/lotr.seuss
$ ./target/release/seuss export examples/lotr.seuss --format svg --output timeline.svg
```

3. `Seuss` provides all the below commands [out-of-the-box](https://en.wikipedia.org/wiki/Out_of_the_Box).

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

...