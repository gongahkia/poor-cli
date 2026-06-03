[![](https://img.shields.io/badge/haus_1.0.0-passing-green)](https://github.com/gongahkia/haus/releases/tag/1.0.0)
![](https://github.com/gongahkia/haus/actions/workflows/ci.yml/badge.svg)
<!-- mcp-name: io.github.gongahkia/haus -->

# `Haus`

AI-agent interior design for Singapore HDB/BTO flats, powered by MCP.

`Haus` turns real public-housing floor plans into a browser-based 3D layout editor that agents can operate with tools: place furniture, tag rooms, check walkways and sightlines, then export JSON, SVG, or GLB layouts.

<div align="center">
  <a href="./asset/demo/hero.mp4">
    <img src="./asset/demo/hero.gif" alt="Demo: prompt Haus to design a minimalist 4-room family flat while MCP tools furnish the BTO layout." width="720">
  </a>
  <br>
  <sub>Prompt: <code>design a minimalist 4-room family flat</code>. Click the demo for the 1080p MP4.</sub>
</div>

## Try the demo

One-command launch, no source checkout:

```console
$ uvx --from git+https://github.com/gongahkia/haus haus view
```

In the browser, open **Chat**, save an Anthropic/OpenAI/Gemini key in **Settings**, then try:

```text
design a minimalist 4-room family flat
```

To connect an MCP client to the same live layout:

```console
$ uvx --from git+https://github.com/gongahkia/haus haus mcp --layout ~/.haus/viewer/mcp-layout.json
```

`uvx haus view` and `pipx install haus` are the intended short forms after a PyPI release; until then, use the GitHub `uvx --from` command above.

**HDB/BTO glossary:** HDB is Singapore public housing; BTO means Build-To-Order, a flat sold from floor-plan brochures before construction.

## Why it matters

* **Agent-native layout editing:** AI clients call MCP tools against real room objects instead of returning a static image.
* **Singapore-specific floor plans:** the corpus is built around HDB/BTO apartment layouts, not generic showrooms.
* **Exportable design state:** the editor keeps measurable 3D geometry that can be saved as JSON, SVG, or GLB.

## Source checkout usage

The below instructions are for developing `Haus` from a local checkout.

1. First run the below instructions to install `Haus` on your machine and install dependencies.

```console
$ git clone https://github.com/gongahkia/haus && cd haus
$ make setup
```

2. Then run any of the below commands.

```console
$ make build # process all corpus images
$ make view # launch web editor
$ make vectorize # run vectorization script only
$ make mcp # run standalone MCP server on stdio only
$ make test # run pytest suite only
$ make lint # run ruff linter only
$ make clean # remove build artifacts
$ make all # run linter, tests and build script
```

## Screenshots

![](./asset/reference/1.png)
![](./asset/reference/2.png)
![](./asset/reference/4.png)
![](./asset/reference/5.png)
![](./asset/reference/6.png)
![](./asset/reference/3.png)

## MCP server

`Haus`' MCP server exposes [a broad tool surface](#mcp-tool-reference) that integrates with the AI Chat within its web editor. It writes to `viewer/mcp-layout.json`, which the web editor polls every 2 seconds.

MCP registry/listing metadata lives in [`mcp-manifest.json`](./mcp-manifest.json), [`server.json`](./server.json), and [`MCP_REGISTRY_LISTINGS.md`](./MCP_REGISTRY_LISTINGS.md).

## MCP tool reference

| Category | Tools |
|---|---|
| **High-level design** | `design_room`, `design_flat` |
| **Catalog** | `list_furniture_catalog` |
| **Layout queries** | `list_objects`, `get_object_details`, `get_layout_summary`, `get_layout_json` |
| **Spatial** | `measure_distance`, `find_nearest`, `check_overlap`, `find_objects_in_area` |
| **Add** | `add_furniture`, `add_wall` |
| **Modify** | `move_object`, `rotate_object`, `resize_object`, `set_color`, `set_visibility` |
| **Batch** | `batch_move`, `align_objects`, `distribute_objects`, `snap_to_grid` |
| **Duplicate/Swap** | `duplicate_object`, `swap_furniture` |
| **Remove** | `remove_object`, `remove_objects_by_type`, `clear_layout` |
| **Naming/Rooms** | `rename_object`, `find_by_name`, `tag_room`, `list_rooms`, `compute_room_area` |
| **Sightlines/Access** | `check_sightline`, `score_doorway_accessibility`, `score_walkway` |
| **Placement simulation** | `suggest_furniture_placement`, `auto_place_furniture`, `suggest_placement_json`, `simulate_layout_options`, `apply_simulated_option` |
| **Room templates** | `list_room_templates`, `apply_room_template` |

## Stack

* *Frontend*: [JavaScript](https://developer.mozilla.org/en-US/docs/Web/JavaScript), [Three.js](https://threejs.org/)
* *Backend*: [Python](https://www.python.org/), [Starlette](https://www.starlette.io/), [Uvicorn](https://www.uvicorn.org/), [FastMCP](https://github.com/jlowin/fastmcp)
* *Preprocessing*: [OpenCV](https://opencv.org/), [NumPy](https://numpy.org/), [Pillow](https://pillow.readthedocs.io/)
* *3D*: [Trimesh](https://trimesh.org/), [Shapely](https://shapely.readthedocs.io/)
* *Tests*: [pytest](https://docs.pytest.org/), [ruff](https://docs.astral.sh/ruff/), [pyright](https://github.com/microsoft/pyright)
* *Package manager*: [uv](https://docs.astral.sh/uv/)

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
