[![](https://img.shields.io/badge/haus_1.0.0-passing-green)](https://github.com/gongahkia/haus/releases/tag/1.0.0)
![](https://github.com/gongahkia/haus/actions/workflows/ci.yml/badge.svg)

# `Haus`

...

> [!IMPORTANT]
> See [here](#credits) for attribution!

## Stack

* *Frontend*: [JavaScript](https://developer.mozilla.org/en-US/docs/Web/JavaScript), [Three.js](https://threejs.org/) 
* *Backend*: [Python](https://www.python.org/), [Starlette](https://www.starlette.io/), [Uvicorn](https://www.uvicorn.org/), [FastMCP](https://github.com/jlowin/fastmcp)
* *Preprocessing*: [OpenCV](https://opencv.org/), [NumPy](https://numpy.org/), [Pillow](https://pillow.readthedocs.io/)
* *3D*: [Trimesh](https://trimesh.org/), [Shapely](https://shapely.readthedocs.io/)
* *Tests*: [pytest](https://docs.pytest.org/), [ruff](https://docs.astral.sh/ruff/), [pyright](https://github.com/microsoft/pyright)
* *Package manager*: [uv](https://docs.astral.sh/uv/)

## Screenshots

![](./asset/reference/1.png)
![](./asset/reference/2.png)
![](./asset/reference/4.png)
![](./asset/reference/5.png)
![](./asset/reference/6.png)
![](./asset/reference/3.png)

## Usage

The below instructions are for locally hosting `Haus`.

1. First run the below instructions to install `Haus` on your machine and install dependancies.

```console
$ git clone https://github.com/gongahkia/haus && cd haus
$ make setup
```

2. Then run any of the below commands.

```console
$ make build # process all corpus images
$ make view # launch web editor 
$ make vectorizez # run vectorization script only 
$ make mcp # run standalone MCP server on stdio only
$ make test # run pytest suite only
$ make lint # run ruff linter only
$ make clean # remove build artifacts 
$ make all # run linter, tests and build script
```

## MCP server

`Haus`' MCP server exposes [30 tools](#mcp-tool-reference) that integrates with the AI Chat within its web editor. It's pretty rudimentary for now and just CRUDS to `viewer/mcp-layout.json`, which the web editor polls every 2 seconds.

## MCP tool reference

| Category | Tools |
|---|---|
| **Catalog** | `list_furniture_catalog` |
| **Layout queries** | `list_objects`, `get_object_details`, `get_layout_summary`, `get_layout_json` |
| **Spatial** | `measure_distance`, `find_nearest`, `check_overlap`, `find_objects_in_area` |
| **Add** | `add_furniture`, `add_wall` |
| **Modify** | `move_object`, `rotate_object`, `resize_object`, `set_color`, `set_visibility` |
| **Batch** | `batch_move`, `align_objects`, `distribute_objects`, `snap_to_grid` |
| **Duplicate/Swap** | `duplicate_object`, `swap_furniture` |
| **Remove** | `remove_object`, `remove_objects_by_type`, `clear_layout` |
| **Naming/Rooms** | `rename_object`, `find_by_name`, `tag_room`, `list_rooms`, `compute_room_area` |

## Providers

`Haus`' AI chat panel supports the below 3 LLM providers currently.

| Provider | Env var | Default model | Install extra |
|---|---|---|---|
| [Anthropic](https://www.anthropic.com/) | `ANTHROPIC_API_KEY` | `claude-sonnet-4-20250514` | `uv pip install -e ".[anthropic]"` |
| [OpenAI](https://openai.com/) | `OPENAI_API_KEY` | `gpt-4o` | `uv pip install -e ".[openai]"` |
| [Google Gemini](https://ai.google.dev/) | `GEMINI_API_KEY` | `gemini-2.0-flash` | `uv pip install -e ".[gemini]"` |

## Architecture

![](./asset/reference/architecture.png)

## Credits

The idea for `Haus` was first conceived by [Zane](https://github.com/injaneity) and iterated on by [Wei Sin](https://github.com/weisintai) for the [OpenAI Codex Hackathon 2026](https://luma.com/fbhtrpfu?tk=1rZbrF), though it was later dropped in favour of [`codex-together`](https://github.com/injaneity/codex-together).

<table>
	<tbody>
        <tr>
            <td align="center">
                <a href="https://github.com/injaneity">
                    <img src="https://avatars.githubusercontent.com/u/44902825?v=4" width="100;" alt=""/>
                    <br />
                    <sub><b>Zane Chee</b></sub>
                </a>
                <br />
            </td>
            <td align="center">
                <a href="https://github.com/weisintai">
                    <img src="https://avatars.githubusercontent.com/u/59339889?v=4" width="100;" alt=""/>
                    <br />
                    <sub><b>Tai Wei Sin</b></sub>
                </a>
                <br />
            </td>
        </tr>
	</tbody>
</table>

## Other research

* [CubiCasa5k](https://github.com/CubiCasa/CubiCasa5k): Deep learning model for floor plan segmentation 

## Reference

The name `Haus` roughly translates to "House" in German (*das Haus*).

<div align="center">
  <img src="./asset/logo/haus.png">
</div>