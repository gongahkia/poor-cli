# Workstream A: Workspace Shell and Information Architecture

Owner goal: build the new unified `/workspace` shell and simplify top-level navigation.

## Owned Write Scope
- `frontend/app/workspace/page.tsx` (new)
- `frontend/components/workspace/**` (new)
- `frontend/app/layout.tsx`
- `frontend/components/side-nav.tsx`

## Do Not Edit
- `frontend/lib/api-client.ts`
- `frontend/lib/api-server.ts`
- `backend/**`

## Tasks
1. Add a new `workspace` route as the primary interaction surface with 3 panes:
   - left: project/session navigator
   - center: conversation/composer region
   - right: inspector panel (sources/citations/artifacts)
2. Update sidebar IA:
   - keep only core entries (`Workspace`, `Benchmarks`, `Settings`, optional `Legacy`)
   - move legacy tool pages under a collapsible "Legacy Tools" group.
3. Ensure mobile behavior is explicit:
   - left rail collapses cleanly
   - no hidden navigation state traps
4. Fix Home routing assumptions by making root route point users to `/workspace` or render a clear CTA to enter workspace.

## Acceptance Criteria
- `/workspace` renders and is reachable from sidebar.
- No dead links from nav (including Home behavior).
- Navigation architecture is task-first, not page-per-tool.
- Existing legacy routes still accessible.

## Validation
- Manual route smoke: `/`, `/workspace`, `/chat`, `/research`, `/contracts`, `/settings`
- Keyboard navigation checks in sidebar and pane toggles

