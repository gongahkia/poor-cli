# Haus Product Expansion and Value Proposition

## 1) Repository Structure, Purpose, and Intent

`haus` is a hybrid project with three core layers:

- `src/haus/`: Python backend for floor-plan vectorization, GLB generation, MCP tool server, and AI chat API.
- `viewer/`: Browser-based 3D editor (Three.js) with object manipulation, export/import, and AI chat operations.
- `tests/`: Backend extraction + pipeline tests (now expanded with MCP simulation tests).

Original intent was strong on technical pipeline output (raster floor plan -> vector + mesh), but underdeveloped in product guidance and AI-assisted decision quality for real household planning.

## 2) Philosophical Value Proposition (Before vs After)

### Before

- Strong conversion pipeline and useful manual editor controls.
- AI chat existed, but mostly as direct CRUD over layout state.
- Minimal support for ambiguous user intent.
- Silent failures in several editor/network paths made debugging harder.

### After this upgrade

`haus` is repositioned as a practical **layout reasoning assistant**, not just a geometry editor:

- Supports vague planning intents through simulation-backed tools.
- Adds explicit spatial reasoning primitives (sightline checks and ranked placement suggestions).
- Preserves user trust with stronger logging, request tracing, and non-silent error paths.
- Improves chat usability for everyday users while keeping low-level controls for developers.

## 3) What Was Added/Upgraded

## Backend and MCP

- Hardened layout read/write flow with normalization + corruption recovery.
- Added simulation and spatial reasoning tools:
  - `check_sightline`
  - `suggest_furniture_placement`
  - `auto_place_furniture`
  - `simulate_layout_options`
  - `apply_simulated_option`
- Improved index validation and safer geometry handling.
- Added central logging utility with rotating file logs (`src/haus/logging_utils.py`).

## Chat Server

- Request-scoped tracing (`request_id`) and tool-action timing logs.
- Removed cross-request shared mutable tool log behavior.
- Improved JSON validation and error response consistency.
- Exposed new simulation/sightline toolchain to chat providers.

## Frontend Chat UX

- Upgraded AI panel to first-class planner UI:
  - Provider selector + optional model override input.
  - Quick intent chips for vague prompts.
  - Conversation clear/reset action.
  - Persisted chat history/transcript and selected provider/model in browser storage.
  - Richer tool-action traces in chat output.
- Removed silent editor sync failures and surfaced actionable warnings for GLB/sync/import errors.

## Testing

- Added `tests/test_mcp_server.py` to cover:
  - Sightline blocking detection.
  - Candidate placement simulation.
  - Simulate/apply flow.
  - Corrupt layout recovery behavior.

## 4) AI Chat as a First-Class Product Feature

The intended workflow for vague requests is now:

1. Summarize current layout context.
2. Simulate candidates against constraints (distance, collisions, room tags).
3. Evaluate sightlines and blockers.
4. Apply chosen option with explicit action log.

Example request style supported:

- "Place the sofa where I can see the TV without being blocked."

Expected behavior now:

- Use simulation tools first.
- Return ranked options.
- Apply selected candidate using deterministic MCP actions.

## 5) Robustness and Debugging Philosophy

Adopted policy:

- No silent failure in critical IO/sync paths.
- Log all tool actions with elapsed time and request trace IDs.
- Normalize layout payloads before persistence.
- Recover from corrupt persisted layout state safely.

This improves reproducibility for developers and confidence for non-technical users.

## 6) Why This Better Serves Developers and Everyday Users

### Developers

- Better observability and deterministic behavior for integration/debugging.
- Expanded MCP primitive set allows building smarter orchestrators.
- Added test coverage around high-risk AI tooling behavior.

### Everyday Users

- Can express goals in natural terms instead of exact coordinates.
- Gets option-driven planning for rooms (not just raw edits).
- Clearer feedback when sync/import/network issues happen.

## 7) Market-Conventions Alignment (Research-Informed)

Current room-planning market expectations consistently include:

- Easy 2D/3D editing and broad furniture catalogs.
- AI-assisted layout generation/rearrangement.
- Import/export and sharing workflows.
- Practical placement quality (clearances, visibility, ergonomics).

Relevant references:

- Sweet Home 3D features (2D/3D, catalog, import/export, plugin model):
  - https://www.sweethome3d.com/features.jsp
- Floorplanner positioning (browser-first, accessibility, fast planning):
  - https://floorplanner.com/
  - https://floorplanner.com/about
- Planner 5D AI Designer workflows (auto-furnish/style/rearrange):
  - https://support.planner5d.com/en/articles/9310416-ai-designer-design-with-ai-web
  - https://support.planner5d.com/en/articles/9310427-ai-designer-create-a-design-using-ai-android
- IKEA Kreativ capability model for room capture + furniture interaction:
  - https://support.home-design.ikea.com/hc/en-no/articles/360038999793-What-can-I-design-in-my-space
- TV distance/sightline relevance for living-room planning:
  - https://www.rtings.com/tv/reviews/by-size/size-to-distance-relationship
- Accessibility baseline references (clear widths / maneuverability):
  - https://www.ada.gov/assets/pdfs/2010-design-standards.pdf

## 8) Local Quality Gate

Run these locally before release:

```bash
ruff check src/ tests/
pyright src/
pytest tests/ -q
```

These mirror the existing `.github/workflows/ci.yml` checks.

## 9) Suggested Next Iteration

- Add explicit doorway/walkway accessibility scoring as MCP tools.
- Add room-template generators (work-from-home, family, rental-ready presets).
- Add optional explainable score breakdowns per simulation candidate in structured JSON mode.
- Add visual overlays for computed sightlines directly in the editor canvas.
