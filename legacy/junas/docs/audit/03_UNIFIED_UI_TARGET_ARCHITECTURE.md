# Unified UI Target Architecture

Objective: centralize Junas into one coherent interaction framework that is easier to learn and faster to use.

## Current Problem Shape
- Tool-first route sprawl: users choose a page before expressing intent.
- Inconsistent execution surfaces (server GET pages vs client fetch pages vs chat commands).
- No single context container across search, analysis, drafting, and prediction.

## Target Product IA

## 1) Single Primary Surface
- Route: `/workspace` (new default landing for logged-in users)
- Core layout:
  - Left rail: projects/sessions + minimal mode switcher
  - Center: conversation + prompt/composer
  - Right panel: citations, sources, artifacts, and run details

## 2) Tool Invocation Model
- One composer entry point (natural language + optional structured form chips).
- Tool calls represented as typed actions in-thread:
  - `search.cases`
  - `search.statutes`
  - `analyze.contract`
  - `analyze.ner`
  - `draft.template`
  - `predict.*`
- Results return as structured cards with a consistent schema and optional deep-link drilldown.

## 3) Context Model
- Workspace/project-level memory:
  - selected jurisdiction
  - uploaded files
  - active conversation thread
  - recent tool outputs
- All tools can consume shared context; user can override per action.

## 4) UX Contract
- Always show:
  - current status (queued/running/done/error)
  - source/citation confidence
  - next-step affordances ("refine", "switch tool", "export", "compare")
- Never require users to re-enter large text when switching capabilities.

## 5) API Access Strategy
- Replace route-specific frontend fetch behavior with one typed SDK.
- Introduce optional orchestration endpoint:
  - `POST /api/v1/workspace/actions`
  - dispatches validated tool action payloads and returns normalized action results.
- Preserve existing endpoints short-term for compatibility.

## Migration Mapping
- Keep existing routes for now as thin wrappers that render the new workspace state.
- Gradually re-route nav:
  - `/chat` -> `/workspace`
  - `/research` -> `/workspace?tool=research`
  - `/contracts` -> `/workspace?tool=contract-analysis`
  - etc.

## Success Criteria
- New users can complete top 5 legal workflows without page-hopping.
- All tool runs expose consistent loading/error/retry states.
- No sensitive long-form legal text appears in URL query strings.
- Command palette, slash commands, and sidebar use the same capability registry.

