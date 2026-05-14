# Pivot Notes

## Phase 4 Integration

- Junas history was imported by subtree under `legacy/junas/`; the working files are removed after the selective web lift, but the commits remain reachable through git history.
- The web app is registered as an npm workspace under `apps/web`.
- Reusable Junas web pieces lifted into `apps/web`: limited Radix primitives, Tailwind token pattern, markdown rendering, Mermaid rendering, Graphviz component scaffold, DOMPurify sanitizers, PDF export shape, and a narrow Fuse.js search suggestion ranker.
- The AI provider layer is fresh scaffolding inspired by Junas's multi-provider concept. It supports Anthropic, OpenAI, and Google only, reads server-side environment variables, and is not wired into the v1 UI.

## Deferred

- PlantUML rendering is deferred pending a self-hosted renderer story; the Junas component calls `plantuml.com`.
- D2 rendering is deferred pending a local or WASM renderer; the Junas component opens `play.d2lang.com`.
- Compromise.js entity extraction is deferred until Dude has a pasted-text input flow that needs local entity detection.
- Graphviz keeps a component scaffold, but `@viz-js/viz` is not added until relationship graphs ship.
- `sg_business_dossier` currently exposes requested `sectorHints` and selected modules, but not an inferred-sector label. The Dude UI skips a "Sector inferred" badge until the envelope exposes that explicitly.
- User accounts, saved searches, monitoring, alerts, payments, bulk lookups, public API access, and AI synthesis remain out of scope for v1.

## Open Decisions

- Root npm package rename is still pending Phase 5 package-name selection.
- GitHub repository rename remains manual and out of scope for Codex.
