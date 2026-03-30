# TODO — 30 March 2026

## Remaining work before calling the repo fully stub-free

1. Implement `Clear Layout` command palette action.
- File: `viewer/js/commandpalette.js`
- Current state: still a placeholder comment (`/* call MCP clear if available */`).
- Needed: wire this command to an actual clear workflow (local scene clear + synced `/api/sync-layout` push, and optional MCP `clear_layout` confirmation path).

## Important follow-up (not stubs, but still unfinished depth)

2. Add visual sightline overlays in-editor.
- Show ray/blocked segments and blockers when AI uses `check_sightline`.

3. Add automated tests for chat API behavior.
- Provider routing, request validation, and action-log payload shape.

4. Add frontend E2E checks for chat + sync resilience.
- Failed sync retries, malformed layout import handling, and transcript persistence.

5. Expand simulation beyond axis-aligned AABB heuristics.
- Better geometric occlusion fidelity and scored accessibility clearances.
