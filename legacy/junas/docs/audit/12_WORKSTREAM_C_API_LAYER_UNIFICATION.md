# Workstream C: API Layer Unification (Frontend)

Owner goal: create one typed frontend API access layer for both client and server usage.

## Owned Write Scope
- `frontend/lib/api-client.ts`
- `frontend/lib/api-server.ts`
- `frontend/lib/api/**` (new, recommended)

## Do Not Edit
- `frontend/app/**/page.tsx` UI behavior beyond import-path adjustments
- Backend routers/services

## Tasks
1. Define a shared typed API contract module:
   - endpoint request/response types
   - common error envelope (`{ error, detail?, status? }`)
2. Refactor `api-client.ts` and `api-server.ts` to use shared endpoint builders and typed decoders.
3. Remove direct `NEXT_PUBLIC_API_URL` + `/api/v1` string repetition in feature pages by exporting a canonical request helper.
4. Add consistent handling for:
   - transport errors
   - non-2xx responses
   - empty payloads

## Acceptance Criteria
- No duplicated endpoint strings across multiple frontend modules where avoidable.
- Client and server wrappers return consistent shapes.
- Existing pages compile with minimal behavior change.

## Validation
- Typecheck passes for frontend.
- Smoke-call representative endpoints:
  - health, chat, research, contracts, benchmarks, statutes.

