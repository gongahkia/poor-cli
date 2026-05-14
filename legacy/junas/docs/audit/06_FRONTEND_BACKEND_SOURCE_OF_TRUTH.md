# Frontend/Backend Source of Truth Cutover

Date: 2026-04-03

## Decision

`frontend/` + `backend/` is the canonical product stack.

`src/` + `src-tauri/` is legacy and will be removed after parity and stabilization.

## Why

1. The web platform already contains the broadest active feature surface.
2. Porting Python backend + ML orchestration into Rust/Tauri is significantly more expensive than porting remaining desktop UX behavior into Next/FastAPI.
3. Existing infrastructure (Docker, Makefile, backend routers/services) aligns with backend-led evolution.

## Target State

1. Primary workflows ship in `frontend/` + `backend/`.
2. Legacy desktop stack is removed from mainline after cutover gates.
3. Desktop returns later as a thin wrapper that hosts the web app, not a separate product stack.

## Cutover Gates

1. Functional parity for high-frequency user journeys:
   - chat and commands
   - legal research and citations
   - contract analysis and compliance
   - templates and clauses
2. Security parity:
   - no long-form legal text in URL query strings
   - centralized sanitization policy for rendered HTML/markdown
3. Reliability parity:
   - stable frontend build/lint checks
   - backend router test baseline green in default CI profile
4. Product parity:
   - unified workspace/navigation behavior
   - command registry and command handler parity

## Decommission Sequence

1. Freeze new feature work in `src/` and `src-tauri/`.
2. Complete parity backlog in `frontend/` + `backend/`.
3. Remove legacy desktop directories and desktop-only pipeline.
4. Re-introduce desktop as a wrapper around the stabilized web stack.

## Rollback Strategy

1. Keep cutover changes atomic and reversible.
2. Use short, focused commits with 5-10 word messages.
3. Avoid mixed concerns across product, infra, and docs in one commit.
