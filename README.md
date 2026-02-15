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
| `seuss export <file.seuss> --format png` | Export as PNG |
| `seuss export <file.seuss> --format pdf` | Export as PDF |
| `seuss check <file.seuss>` | Validate without rendering |

4. Also navigate `Seuss`' TUI with the following commands.

| Key | Action |
|-----|--------|
| `h/j/k/l` or arrows | Pan viewport |
| `+/-` | Zoom in/out |
| `Tab` | Cycle entity selection |
| `Enter` | Focus on selected entity |
| `/` | Search entities |
| `?` | Toggle help |
| `q` | Quit |

## Syntax

Learn more about `Seuss`' syntax at [`SYNTAX.md`](./docs/SYNTAX.md).

Alternatively, refer to examples which live at [`./examples`](./examples/).

## Architecture

<div align="center">
    <img src="./asset/reference/architecture.png">
</div>