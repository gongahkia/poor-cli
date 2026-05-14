# Workstream E: Tool Migration into Unified Workspace

Owner goal: migrate legacy page-specific workflows into workspace-style tool panels and remove high-risk GET submissions.

## Owned Write Scope
- `frontend/app/contracts/page.tsx`
- `frontend/app/research/page.tsx`
- `frontend/app/search/page.tsx`
- `frontend/app/ner/page.tsx`
- `frontend/app/predictions/page.tsx`
- `frontend/app/compliance/page.tsx`
- `frontend/app/clauses/page.tsx`
- `frontend/app/templates/page.tsx`
- Optional wrappers for:
  - `frontend/app/legal-sources/page.tsx`
  - `frontend/app/compare-jurisdictions/page.tsx`

## Do Not Edit
- Core API wrappers (`frontend/lib/api-client.ts`, `frontend/lib/api-server.ts`) except import adaptation.
- Backend routers/services.

## Tasks
1. Replace `method="get"` large-text forms with POST/action-style invocations.
2. Move tool execution UI into reusable workspace panels/components.
3. Standardize status handling:
   - loading
   - empty
   - success
   - recoverable error with retry
4. Ensure jurisdiction/file context can be reused across tools without re-entry.
5. Keep legacy route URLs working (as wrappers), but render workspace-backed components.

## Acceptance Criteria
- No long-form legal text in URL query strings for migrated tools.
- Migrated tools share a common interaction skeleton.
- Tool switching preserves user context where expected.

## Validation
- End-to-end manual flows:
  - research question -> cited answer
  - contract text -> classification + ToS scan
  - NER extraction
  - prediction task run

