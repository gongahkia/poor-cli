# Nielsen Heuristics Audit (Junas Frontend)

Reference framework: Jakob Nielsen's 10 usability heuristics (NN/g)

Source:
- https://www.nngroup.com/articles/ten-usability-heuristics/

## Heuristic Matrix

| Heuristic | Current State | Evidence | Risk | Priority |
|---|---|---|---|---|
| 1. Visibility of system status | Partial | Loading indicators exist in some client pages, but silent catches suppress failures (e.g. compliance `catch {}`) | Users cannot distinguish "no results" vs "request failed" in several modules | High |
| 2. Match with real world | Mixed | Navigation categories are domain-labeled, but users must pre-select tool before describing task intent | Mental model is tool-first, not legal-problem-first | High |
| 3. User control and freedom | Mixed | Chat supports stop + branch editing; many pages do not support undo/iteration paths | Users restart flows when wrong mode selected | Medium |
| 4. Consistency and standards | Weak | Mixed server GET forms, client fetch pages, and direct fetch in components | Inconsistent interaction and failure behavior across modules | High |
| 5. Error prevention | Weak | Long legal text sent through query params (`method="get"` forms) | Privacy leakage and URL length errors are avoidable but currently allowed | Critical |
| 6. Recognition over recall | Partial | Sidebar exposes many modules but no unified command-to-tool guidance outside chat | Users must remember where each capability lives | High |
| 7. Flexibility and efficiency | Partial | Keyboard shortcuts exist in chat, but no global command interface across all work | Power-user efficiency limited to one module | Medium |
| 8. Aesthetic and minimalist design | Mixed | Good global tokens exist in CSS, but heavy inline style sprawl (194 occurrences) | Visual inconsistency and hard-to-maintain UI behavior | High |
| 9. Help users recover from errors | Weak | Generic/hidden errors in many client calls; test suite tolerates server failures | Hard to diagnose failures and recover in-flow | High |
| 10. Help and documentation | Partial | README exists but architecture counts are stale, and no in-product task guidance | Onboarding and feature discovery remain expensive | Medium |

## Key Evidence Pointers
- GET forms with large text payloads:
  - [frontend/app/contracts/page.tsx](../../frontend/app/contracts/page.tsx#L106)
  - [frontend/app/research/page.tsx](../../frontend/app/research/page.tsx#L154)
  - [frontend/app/search/page.tsx](../../frontend/app/search/page.tsx#L96)
  - [frontend/app/ner/page.tsx](../../frontend/app/ner/page.tsx#L140)
- Broken home navigation route:
  - [frontend/components/chat/CommandPalette.tsx](../../frontend/components/chat/CommandPalette.tsx#L7)
  - [frontend/components/chat/CommandPalette.tsx](../../frontend/components/chat/CommandPalette.tsx#L50)
- Command mismatch:
  - [frontend/components/chat/CommandSuggestions.tsx](../../frontend/components/chat/CommandSuggestions.tsx#L11)
  - [frontend/lib/commands/command-handler.ts](../../frontend/lib/commands/command-handler.ts#L16)
- Error handling gaps:
  - [frontend/app/compliance/page.tsx](../../frontend/app/compliance/page.tsx#L26)
  - [frontend/app/clauses/page.tsx](../../frontend/app/clauses/page.tsx#L16)
  - [frontend/app/templates/page.tsx](../../frontend/app/templates/page.tsx#L15)

## Heuristic-Driven UX Target
- Replace multi-page tool-first journey with one intent-first workspace.
- Standardize async states: loading, partial, success, empty, recoverable error.
- Convert sensitive text workflows to POST-backed mutations and session state.
- Build one consistent component system for forms, results, and citations.

