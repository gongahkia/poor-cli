[![](https://img.shields.io/badge/haus_0.1.0-passing-green)](https://github.com/gongahkia/haus/releases/tag/0.1.0)
![](https://github.com/gongahkia/haus/actions/workflows/ci.yml/badge.svg)
<!-- mcp-name: io.github.gongahkia/haus -->

# `Haus`

Concept planning and spatial validation workbench for uploaded apartment layouts.

`Haus` turns a floor plan into actionable layout options, checks, and client-ready exports. Upload or trace a plan, calibrate scale, compare scenarios, run renovation/accessibility/furniture-fit checks, and export local JSON, SVG, PNG, HTML, or GLB artifacts. It runs locally and exposes an MCP server so agents can work against real layout objects instead of static images.

<div align="center">
  <a href="./asset/demo/hero.mp4">
    <img src="./asset/demo/hero.gif" alt="Demo: use Haus to draft, validate, and export apartment planning scenarios." width="720">
  </a>
  <br>
  <sub>Sample prompt: <code>draft three renovation options and show validation warnings before export</code>.</sub>
</div>

## Try It

One-command launch:

```console
$ uvx --from git+https://github.com/gongahkia/haus haus view
```

In the editor:

1. Click **Upload Plan** or use **Tools -> Upload Floor Plan**.
2. Optionally enter a known pixel length and real-world length for calibration.
3. Review extracted walls/openings.
4. Pick Renovation, Accessibility, Furniture Fit, Designer, or Blank Project.
5. Ask the planner to draft, revise, validate, apply, compare, or export a scenario.

Example prompts:

```text
Draft three renovation concepts with conservative, balanced, and ambitious options.
Run an accessibility review for a walker user and show blocked routes.
Check whether this sofa fits in the living room and through the entry path.
Create a client-ready pre-sales summary for this floor plan.
```

To connect an MCP client to the same live layout:

```console
$ uvx --from git+https://github.com/gongahkia/haus haus mcp --layout ~/.haus/viewer/mcp-layout.json
```

`uvx haus view` and `pipx install haus` are the intended short forms after a PyPI release; until then, use the GitHub `uvx --from` command above.

## Four Customer Journeys

| Journey | Use it for | Try this prompt | Demo |
|---|---|---|---|
| Renovation | Compare conservative, balanced, and ambitious concept options before changing walls, openings, or services. | `Draft three renovation options and flag what needs professional verification.` | [screenshot](./asset/demo/journeys/renovation.png), [sample report](./asset/demo/reports/renovation-concept-pack.md) |
| Accessibility | Find blocked routes, narrow openings, turning risks, trip hazards, and practical quick wins. | `Run a wheelchair accessibility review and separate quick wins from renovation work.` | [screenshot](./asset/demo/journeys/accessibility.png), [sample report](./asset/demo/reports/accessibility-review.md) |
| Furniture Fit | Check product dimensions, clearance, delivery assumptions, substitutes, and shopping-list export before buying. | `Check if this sofa fits, suggest smaller substitutes, and export a shopping list.` | [screenshot](./asset/demo/journeys/furniture-fit.png), [sample report](./asset/demo/reports/furniture-fit-report.md) |
| Designer | Turn intake notes into a client-safe pre-sales brief, branded report, call script, and presentation view. | `Create a client pre-sales pack from this design brief and selected scenario.` | [screenshot](./asset/demo/journeys/designer.png), [sample report](./asset/demo/reports/designer-pre-sales-pack.md) |

## What It Does

* **Journey-first planning:** choose Renovation, Accessibility, Furniture Fit, Designer, or Blank Project and keep that context in project metadata and chat.
* **Measured layout editing:** calibration and confidence metadata keep furniture, walls, checks, and exports in meters.
* **Scenario validation:** compare layout versions, assumptions, unknowns, warnings, and room-by-room validation results before applying a plan.
* **Useful fallbacks:** if extraction is weak, load the image as a reference overlay and open manual tracing tools immediately.
* **Local-first exports:** save JSON, SVG, GLB, screenshots, shopping lists, and standalone HTML/print reports.

## Launch Assets

* Demo screenshots live in [`asset/demo/journeys`](./asset/demo/journeys).
* Sample journey reports live in [`asset/demo/reports`](./asset/demo/reports).
* Clean `uvx` smoke tests are documented in [`docs/launch/smoke-tests.md`](./docs/launch/smoke-tests.md), with scripts for Linux and macOS under [`scripts/`](./scripts).
* MCP registry copy is in [`docs/launch/mcp-registry-copy.md`](./docs/launch/mcp-registry-copy.md).

## Source Checkout

```console
$ git clone https://github.com/gongahkia/haus && cd haus
$ make setup
```

Common commands:

```console
$ make view       # launch local editor
$ make build      # process floor plan images in corpus/
$ make vectorize  # vectorize only
$ make mcp        # start standalone MCP server
$ make test       # run pytest suite
$ make lint       # run ruff
$ make all        # lint + test + build
```

Direct CLI usage:

```console
$ haus build --image ./my-floor-plan.png --out ./out/my-plan --scale-override 0.01
$ haus view
```

## Product Boundaries

`Haus` is a concept planning and spatial validation workbench. It is not BIM authoring software, code certification, medical advice, occupational therapy assessment, contractor-ready documentation, a permit package generator, or a substitute for professional site verification. Scale inferred from images is approximate unless calibrated by the user.

Accessibility output is planning guidance only, not ADA certification, medical advice, or an occupational therapy assessment. Renovation wall and plumbing suggestions are concept-only until verified by a qualified professional on site.

Bundled sample layouts are examples only. The product does not depend on a comprehensive BTO/HDB corpus.

Extraction accuracy depends on image quality, scale confirmation, and visible plan symbols. Product dimensions and prices can become stale and should be checked against retailer pages or physical measurements before purchase. Web search and external LLM providers are optional; the local deterministic planner remains available when those are disabled.

## MCP Tool Surface

The MCP surface is meant to support practical floor-plan workflows, not generic scene editing claims. Agents can inspect real layout objects, draft journey-specific options, validate geometry, and export client-readable artifacts.

| Category | Tools |
|---|---|
| **High-level design** | `design_room`, `design_flat` |
| **Catalog** | `list_furniture_catalog`, `search_ikea_catalog`, `get_ikea_catalog_item`, `add_catalog_furniture`, `refresh_ikea_catalog` |
| **Layout queries** | `list_objects`, `get_object_details`, `get_layout_summary`, `get_layout_json` |
| **Spatial** | `measure_distance`, `find_nearest`, `check_overlap`, `find_objects_in_area` |
| **Add/modify** | `add_furniture`, `add_wall`, `move_object`, `rotate_object`, `resize_object`, `set_color`, `set_visibility` |
| **Batch** | `batch_move`, `align_objects`, `distribute_objects`, `snap_to_grid` |
| **Duplicate/remove** | `duplicate_object`, `swap_furniture`, `remove_object`, `remove_objects_by_type`, `clear_layout` |
| **Rooms** | `rename_object`, `find_by_name`, `tag_room`, `list_rooms`, `compute_room_area` |
| **Validation** | `check_sightline`, `score_doorway_accessibility`, `score_walkway`, `score_layout` |
| **Simulation/templates** | `suggest_furniture_placement`, `auto_place_furniture`, `simulate_layout_options`, `apply_simulated_option`, `list_room_templates`, `apply_room_template` |
| **Agent contracts** | `list_constraint_packs`, `get_constraint_pack`, `get_layout_graph_json`, `reason_about_layout`, `get_schema_catalog_json`, `get_multimodal_intake_contract`, `create_scenario_transaction`, `apply_scenario_transaction`, `revert_scenario_transaction`, `run_agent_eval_suite` |
| **Export semantics** | `get_semantic_layout_json`, `bim_readiness_report` |

Agents should treat `get_layout_graph_json` as the canonical reasoning input. It exposes rooms, openings, objects, adjacency, zones, routes, constraint targets, findings, and evidence IDs. Any edit should be emitted as a scenario transaction before it is applied, so the user can inspect the before/after diff and safety confirmation reasons.

MCP resources expose the same contracts without a tool call: `haus://layout/current`, `haus://layout/graph`, `haus://schema/catalog`, `haus://schema/semantic_layout.v1`, `haus://intake/multimodal.v1`, and `haus://scenarios/{scenario_id}/diff`. Prompt templates include `architect_space`, `validate_plan`, `prepare_contractor_questions`, and `furniture_fit_review`.

Constraint packs live as versioned JSON under `src/haus/corpus/constraints/`; bundled packs cover compact HDB/BTO planning, furniture fit/delivery, accessibility, kitchens, bathrooms, rental rooms, and agent guardrails. The bundled eval suite `agent_layout_reasoning.v1` checks golden layout prompts for expected findings, invalid geometry, missing validation, bad scale assumptions, and hallucinated edits.

## Roadmap

Help prioritize the next workflow by opening a [journey feedback issue](./.github/ISSUE_TEMPLATE/journey_feedback.md):

* Homeowner renovation: stronger before/after visuals, contractor question packs, and service-zone constraints.
* Accessibility: richer room-specific checklists, caregiver routes, and OT handoff summaries.
* Furniture fit: deeper catalog provenance, delivery-path checks, and product comparison exports.
* Designer: stronger mood-board assets, branded proposal polish, and client-review handoff bundles.

Future expansion gates are tracked in [`docs/future-evaluations.md`](./docs/future-evaluations.md).

## Stack

* Frontend: JavaScript, Three.js
* Backend: Python, Starlette, Uvicorn, FastMCP
* Preprocessing: OpenCV, NumPy, Pillow
* 3D: Trimesh, Shapely
* Tests: pytest, ruff, pyright, optional Playwright e2e
* Package manager: uv

## Providers

The planner supports these LLM providers through the first-class chat registry. Hosted providers need a key in the editor settings or env; local runtimes use the user's installed/authenticated CLI or local model server.

| Provider | Env/config | Default model | Install extra |
|---|---|---|---|
| Anthropic | `ANTHROPIC_API_KEY` | `claude-sonnet-4-20250514` | `uv pip install -e ".[anthropic]"` |
| OpenAI | `OPENAI_API_KEY` | `gpt-5.5` | `uv pip install -e ".[openai]"` |
| Google Gemini | `GEMINI_API_KEY` | `gemini-2.5-flash` | `uv pip install -e ".[gemini]"` |
| Ollama/local | `OLLAMA_BASE_URL`, `OLLAMA_MODEL` | `llama3.1` | `brew install ollama` |
| Codex runtime | `HAUS_CODEX_MODEL`, `HAUS_CODEX_OSS=1`, `HAUS_CODEX_LOCAL_PROVIDER=ollama`, `HAUS_CODEX_CMD` | `default` | `codex login`, or local OSS provider config |
| Gemini CLI runtime | `HAUS_GEMINI_CLI_MODEL`, `HAUS_GEMINI_CLI_CMD` | `default` | `gemini auth login` |
| Claude Code runtime | `HAUS_CLAUDE_CODE_MODEL`, `HAUS_CLAUDE_CODE_CMD` | `default` | `claude auth login` |
| opencode runtime | `HAUS_OPENCODE_MODEL`, `HAUS_OPENCODE_CMD` | `default` | `opencode providers auth` or local provider config |
| Aider runtime | `HAUS_AIDER_MODEL`, `HAUS_AIDER_CMD` | `default` | `pipx install aider-chat`, plus provider auth/model config |
| OpenAI-compatible local | `HAUS_OPENAI_COMPAT_BASE_URL`, `HAUS_OPENAI_COMPAT_MODEL`, `HAUS_OPENAI_COMPAT_API_KEY` | `local-model` | Start LM Studio, llama.cpp server, vLLM, or LocalAI with `/v1/chat/completions` |
| WebLLM | `HAUS_WEBLLM_MODEL` | `Llama-3.1-8B-Instruct-q4f32_1-MLC` | Use a WebGPU-capable browser; first run downloads model assets into browser cache |

Every configured provider can use the Haus tool surface. Hosted APIs, Ollama, and OpenAI-compatible local servers use their native/OpenAI-style tool path when available. Coding-agent CLIs use a guarded JSON tool-call protocol: Haus passes chat/layout context and tool results, while the CLI is instructed not to edit files, run shell commands, or use runtime-native tools. WebLLM runs in the browser and dispatches Haus tool calls back through the local Haus server.

The editor reads `/api/chat/models` for provider metadata, known model IDs, and capability flags. `/api/chat/stream` emits normalized SSE events for streaming-capable chat clients.

## Credits

The original idea for `Haus` was conceived by [Zane](https://github.com/injaneity) and iterated on by [Wei Sin](https://github.com/weisintai) for the OpenAI Codex Hackathon 2026. This repo now focuses on a general uploaded-floor-plan workbench.

## Reference

The name `Haus` roughly translates to "House" in German.

<div align="center">
  <img src="./asset/logo/haus.png">
</div>
