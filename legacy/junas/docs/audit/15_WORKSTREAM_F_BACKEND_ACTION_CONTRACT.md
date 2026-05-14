# Workstream F: Backend Action Contract and Domain Consistency

Owner goal: expose a normalized backend action interface and fix domain mismatches that hurt unified UX.

## Owned Write Scope
- `backend/api/routers/**` (new router allowed)
- `backend/api/services/**` (new orchestration service allowed)
- `backend/api/main.py` (router registration only)
- `backend/tests/**` for new/updated backend contract tests

## Do Not Edit
- Frontend routes/components

## Tasks
1. Add action orchestration contract (recommended):
   - `POST /api/v1/workspace/actions`
   - request: `{ action_type, payload, context }`
   - response: normalized `{ status, data, sources?, citations?, error? }`
2. Keep existing feature endpoints intact during transition.
3. Fix jurisdiction behavior gaps:
   - compliance endpoints should respect requested jurisdiction or return explicit unsupported error.
4. Ensure consistent error schema across routers.
5. Harden HTML-bearing payload boundaries (sanitize/escape strategy documented and enforced).

## Acceptance Criteria
- Unified action route supports at least 5 representative actions.
- Compliance jurisdiction mismatch is resolved or explicitly constrained.
- Backend error contract is predictable for frontend consumption.

## Validation
- Add contract tests for action route and jurisdiction behavior.
- Regression tests for existing routers remain green.

