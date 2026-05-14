# Revamp Roadmap and Risk Register

## Delivery Phases

## Phase 0: Guardrails (1 sprint)
- Replace high-risk GET text workflows with POST/session-backed calls.
- Fix command palette route bug and command registry mismatch.
- Standardize fetch error handling for all client pages.

Exit criteria:
- No legal text payloads in URL query params for analysis/research flows.
- Command actions are all executable or removed from UI.

## Phase 1: Foundation Unification (1-2 sprints)
- Build shared frontend SDK and typed result envelopes.
- Create core workspace shell (`/workspace`) with common panes.
- Build capability registry used by sidebar + command palette + slash commands.

Exit criteria:
- At least 3 existing modules run through the unified shell.

## Phase 2: Feature Migration (2-4 sprints)
- Migrate search/research/contracts/NER/templates/clauses into workspace tools.
- Add shared citation + artifacts panel.
- Implement cross-tool context carryover (files, jurisdiction, thread state).

Exit criteria:
- Primary user tasks executed end-to-end without page switching.

## Phase 3: Hardening and Cutover (1-2 sprints)
- deprecate legacy route-specific logic.
- add regression tests for action orchestration and UI consistency.
- publish updated docs and migration notes.

Exit criteria:
- Legacy pages are wrappers or removed.
- Metrics show reduced abandonment and faster task completion.

## Risk Register

1. Backward compatibility drift between new workspace actions and legacy endpoints.
Mitigation: adapter layer + contract tests.

2. Performance regression if all tool outputs are streamed into a single UI tree.
Mitigation: virtualized result lists and lazy panel rendering.

3. Security regressions from mixed HTML rendering paths.
Mitigation: sanitization policy + CSP + strict markdown rendering boundaries.

4. Coordination overhead from parallel agent work.
Mitigation: disjoint ownership docs (see `10_*` to `16_*`).

