# Junas Repository Audit (Engineering + UX)

Date: 2026-04-02
Scope: `backend/` + `frontend/` in this repository root

## Snapshot
- Frontend app routes: 20 (`frontend/app/**/page.tsx`)
- Backend API routes: 55 decorators (`backend/api/routers/**`)
- Inline style usage: 194 `style={{...}}` instances across frontend TSX
- Test functions found: 85 in `backend/tests/**`

## Critical Findings
1. Workflow fragmentation is high for end users.
Evidence: 20 sidebar links split across 7 headings in [frontend/components/side-nav.tsx](../../frontend/components/side-nav.tsx#L18).
Impact: users must choose tools before describing intent; this increases cognitive load and hurts discoverability.

2. Sensitive legal text is submitted via URL query params in multiple flows.
Evidence: large textareas posted through `method="get"` in [frontend/app/contracts/page.tsx](../../frontend/app/contracts/page.tsx#L106), [frontend/app/research/page.tsx](../../frontend/app/research/page.tsx#L154), [frontend/app/search/page.tsx](../../frontend/app/search/page.tsx#L96), [frontend/app/ner/page.tsx](../../frontend/app/ner/page.tsx#L140), [frontend/app/predictions/page.tsx](../../frontend/app/predictions/page.tsx#L173).
Impact: privacy risk (browser history/logs/shareable URLs), brittle long-URL behavior, poor legal-product trust posture.

3. Command palette has broken navigation for Home.
Evidence: `nav-home` resolves to `/home` in [frontend/components/chat/CommandPalette.tsx](../../frontend/components/chat/CommandPalette.tsx#L7) and [frontend/components/chat/CommandPalette.tsx](../../frontend/components/chat/CommandPalette.tsx#L50), but no `/home` route exists.
Impact: direct user-facing dead end.

4. Command suggestions advertise commands that are not implemented.
Evidence: commands listed in [frontend/components/chat/CommandSuggestions.tsx](../../frontend/components/chat/CommandSuggestions.tsx#L11) vs implemented switch cases in [frontend/lib/commands/command-handler.ts](../../frontend/lib/commands/command-handler.ts#L16).
Impact: broken expectation, reduced trust in interaction model.

5. Frontend data-access is duplicated and inconsistent.
Evidence: duplicated API wrappers in [frontend/lib/api-client.ts](../../frontend/lib/api-client.ts#L1) and [frontend/lib/api-server.ts](../../frontend/lib/api-server.ts#L1), plus direct `fetch` calls in feature pages like [frontend/app/clauses/page.tsx](../../frontend/app/clauses/page.tsx#L14), [frontend/app/templates/page.tsx](../../frontend/app/templates/page.tsx#L14), [frontend/app/chat/page.tsx](../../frontend/app/chat/page.tsx#L126), [frontend/app/compliance/page.tsx](../../frontend/app/compliance/page.tsx#L18).
Impact: divergent behavior, inconsistent error handling, higher maintenance cost.

6. Jurisdiction behavior is inconsistent with UI claims.
Evidence: compliance request includes `jurisdiction` but backend always uses `DEFAULT_SG_RULES` in [backend/api/routers/compliance.py](../../backend/api/routers/compliance.py#L22).
Impact: user-facing mismatch and correctness risk.

7. Unsafe or unbounded HTML rendering paths exist.
Evidence: `dangerouslySetInnerHTML` usage in [frontend/app/compare-jurisdictions/page.tsx](../../frontend/app/compare-jurisdictions/page.tsx#L99), [frontend/app/statutes/section/[number]/page.tsx](../../frontend/app/statutes/section/[number]/page.tsx#L47), [frontend/app/glossary/[phrase]/page.tsx](../../frontend/app/glossary/[phrase]/page.tsx#L60), and theme injection script in [frontend/app/layout.tsx](../../frontend/app/layout.tsx#L16).
Impact: sanitization and CSP hardening are incomplete.

8. Chat router test accepts broad failure states as success envelope.
Evidence: [backend/tests/test_chat_router.py](../../backend/tests/test_chat_router.py#L20) allows `200, 422, 500, 502`.
Impact: regressions can ship undetected.

## Structural Observation
- Legacy project trees exist at repo root (`junas/`, `openlex/`) and are ignored in git ([.gitignore](../../.gitignore#L1)). This is useful as reference material but increases onboarding ambiguity unless documented explicitly.

## Recommended Product Direction
Move from many feature pages to one unified "Legal Workspace" surface:
- One primary composer for intent capture
- Tool execution as modes/panels, not separate route silos
- Shared citation/source inspector and artifact panel
- Context-preserving sessions/projects (not per-page stateless forms)

This aligns better with current AI UX norms and legal workflow expectations while reducing user learning burden.

