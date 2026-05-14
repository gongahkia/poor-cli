# Junas Full Migration Tasking (Agent-Executable)

Updated: 2026-04-03
Audience: Independent coding agent taking over implementation
Scope: Complete migration to `frontend/` + `backend/` as only source of truth, then remove legacy desktop stack (`src/`, `src-tauri/`), and later re-introduce desktop as a thin web wrapper.

## 1) Mission

Make `frontend/` + `backend/` the only product logic source of truth.

This means:
1. All user-facing workflows run from Next.js + FastAPI.
2. Legacy desktop runtime logic is either migrated, replaced, or intentionally deprecated.
3. `src/` and `src-tauri/` are removed only after parity and stabilization gates pass.
4. Desktop returns later as a thin host shell around the web app, not a second logic stack.

## 2) Non-Negotiable Operating Constraints

## 2.1 Git Commit Requirements (MANDATORY)

1. Every change set must be atomic and rollback-safe.
2. Commit messages must be 5-10 words.
3. Prefer one logical concern per commit.
4. If a change is large, split into micro-commits by file group and behavior.
5. Never batch unrelated infra, feature, and docs changes in one commit.
6. Run at least targeted validation before each commit.

Atomic commit examples (valid length):
- `Migrate research page to client POST flow`
- `Add guardrail test for GET text payloads`
- `Document workspace action contract and error schema`

## 2.2 README Rule (MANDATORY)

1. Do not edit `README.md`.
2. Any documentation change that would normally go to `README.md` must be written to `README2.md`.
3. Additional technical docs should go under `docs/`.

## 2.3 Safety and Editing Constraints

1. Do not revert unrelated user changes.
2. Do not use destructive git commands (`reset --hard`, forced checkout) unless explicitly requested.
3. Keep `frontend/` + `backend/` behavior stable while migrating.
4. Keep compatibility routes until cutover gate says they can be removed.

## 3) Current Snapshot (Already Completed)

Recent commits already landed:
1. `2035167` Implement jurisdiction-aware compliance rules and router behavior.
2. `98ca7ba` Migrate search page to client-side POST flow.
3. `d8e98e5` Migrate NER page to client POST workflow.
4. `54de4e1` Migrate contracts page to client POST submission.
5. `045052d` Migrate predictions suite to client POST forms.

Still outstanding from Phase 0:
1. `frontend/app/research/page.tsx` is still query-param driven and must be migrated.
2. Privacy guardrails need automated test/lint enforcement.
3. Command/runtime parity and sanitization hardening still need structured completion.

## 4) Global Definition of Done

All of the following must be true:
1. No long-form legal text is transmitted via URL query params.
2. Primary user journeys (chat, research, contracts, compliance, templates/clauses) are fully web-stack backed.
3. All command UI entries map to executable behavior or are explicitly disabled.
4. CI must pass with deterministic frontend and backend checks.
5. Legacy `src/` + `src-tauri/` are removed from mainline product logic.
6. Documentation is updated in `README2.md` and `docs/` only.

## 5) High-Level Phases and Dependency Order

Phase dependency order:
1. Phase 0: Guardrails and parity blockers.
2. Phase 1: Foundation unification (`workspace`, API contracts, capability registry).
3. Phase 2: Full feature migration into unified shell and context model.
4. Phase 3: Hardening, action contract stabilization, and cutover checks.
5. Phase 4: Remove `src/` + `src-tauri/` from mainline.
6. Phase 5: Later roadmap - thin desktop wrapper around web app.

Parallelization guidance:
1. Parallel: API contract and backend contract workstreams.
2. Parallel: workspace shell and design system workstreams.
3. Parallel: chat/commands and tool migration workstreams.
4. Finalize with QA, telemetry, docs, and cutover.

## 6) Detailed Task Registry

## Phase 0 - Guardrails (Immediate, Mandatory)

## P0-01: Finish `/research` GET-to-POST migration

Goal: remove query-string payload transport in research flow.

Files:
1. `frontend/app/research/page.tsx`
2. `frontend/lib/api-client.ts` (if helper signatures needed)

Implementation steps:
1. Convert route to client component (`"use client"`).
2. Move form state to local React state:
   - `question`, `conversationId`, `topK`, `selectedSources`, `loading`, `error`.
3. Fetch config (`getResearchConfig`) on mount.
4. Submit via `askResearch(question, sources, topK, conversationId)`.
5. On successful answer, pull conversation via `getResearchConversation(conversationId)`.
6. Keep citation and source rendering exactly functionally equivalent.
7. Add `New Conversation` reset button that clears thread state without URL reload.
8. Remove dependency on `searchParams.question`, `searchParams.run`, and similar URL inputs.

Acceptance criteria:
1. Asking a question never writes legal text to URL.
2. Citations and retrieved source cards still render.
3. Existing model/config metadata still appears.

Validation:
1. `cd frontend && npx tsc --noEmit --pretty false`
2. `cd frontend && npm run lint`
3. Manual: ask 2 sequential questions in same conversation.
4. Manual: verify browser URL has no `question=` payload.

Commit boundary:
1. Commit only research migration files.
2. Example commit: `Migrate research page to client POST flow`.

## P0-02: Add privacy guardrail automation

Goal: prevent regressions that reintroduce text-heavy GET forms.

Files:
1. `scripts/` (new guardrail script, suggested `scripts/check-no-large-get-forms.sh`)
2. `.github/workflows/unified-platform.yml`
3. `package.json` script entry (optional)

Implementation steps:
1. Add script that fails if `frontend/app/**` contains:
   - `method="get"` forms with `textarea`, or
   - encoded text payload URL constructors for large text (`?text=` or `?question=` patterns in submit flows).
2. Allowlist legitimate short query routes if needed (`glossary`, `statutes`, `rome-statute`).
3. Wire script into CI workflow before build.

Acceptance criteria:
1. CI fails when text-heavy GET patterns are introduced.
2. CI passes for current migrated routes.

Validation:
1. Run guardrail script locally.
2. Run frontend build after guardrail.

Commit boundary:
1. Commit script + workflow only.
2. Example commit: `Add CI guardrail for large GET payloads`.

## P0-03: Sanitize rendering policy convergence

Goal: eliminate inconsistent markdown/html rendering safety behavior.

Files:
1. `frontend/components/chat/MarkdownRenderer.tsx`
2. `frontend/components/chat/LegalMarkdownRenderer.tsx`
3. Any shared sanitize utility under `frontend/lib/` (new if needed)

Implementation steps:
1. Define one sanitize policy and apply to both renderers.
2. Ensure links are safe (`rel="noopener noreferrer"` where needed).
3. Ensure raw HTML is either sanitized or disabled consistently.
4. Add tests/smoke checks for script injection strings.

Acceptance criteria:
1. Same input string yields predictable safe rendering across chat renderers.
2. No executable script payload renders.

Validation:
1. `cd frontend && npx tsc --noEmit --pretty false`
2. Add minimal tests if test framework exists for frontend.
3. Manual XSS sanity checks.

Commit boundary:
1. Commit renderer/sanitization changes only.
2. Example commit: `Unify markdown sanitization across chat renderers`.

## P0-04: Command parity and dead-action elimination

Goal: ensure every advertised command is executable or clearly disabled.

Files:
1. `frontend/components/chat/CommandSuggestions.tsx`
2. `frontend/components/chat/CommandPalette.tsx`
3. `frontend/lib/commands/command-handler.ts`
4. `docs/audit/13_WORKSTREAM_D_CHAT_AND_COMMANDS.md` (if documenting final mapping)

Implementation steps:
1. Produce a command parity table from legacy definitions vs frontend handler coverage.
2. Remove dead commands from UI or map them to deterministic responses.
3. Ensure command palette route actions are valid.
4. Add a simple parity test or script to detect drift.

Acceptance criteria:
1. No clickable command results in no-op.
2. All slash suggestions map to handler-supported command IDs.

Validation:
1. Manual smoke for each visible command.
2. Typecheck/lint pass.

Commit boundary:
1. Command system files only.
2. Example commit: `Enforce command registry parity with handler actions`.

---

## Phase 1 - Foundation Unification

## P1-01: Unified API contract module (frontend)

Goal: align `api-client` and `api-server` return envelopes and endpoint typing.

Files:
1. `frontend/lib/api-client.ts`
2. `frontend/lib/api-server.ts`
3. `frontend/lib/api/` (new typed helpers)

Implementation steps:
1. Introduce shared endpoint type contracts.
2. Centralize URL building and error envelope normalization.
3. Ensure both client/server wrappers return consistent success/error shapes.

Acceptance criteria:
1. Feature pages can consume either wrapper predictably.
2. Endpoint string duplication is reduced.

Validation:
1. Frontend typecheck and build.
2. Smoke-call representative endpoints.

Commit boundary:
1. API wrappers only.

## P1-02: Introduce `/workspace` shell

Goal: create task-first unified interaction surface.

Files:
1. `frontend/app/workspace/page.tsx` (new)
2. `frontend/components/workspace/**` (new)
3. `frontend/components/side-nav.tsx`
4. `frontend/app/layout.tsx`

Implementation steps:
1. Implement 3-pane shell (navigator, center workspace, inspector).
2. Route users from `/` to clear workspace entry path.
3. Keep legacy pages reachable during migration.

Acceptance criteria:
1. Workspace route is stable on desktop/mobile.
2. No dead nav links.

Validation:
1. Route smoke: `/`, `/workspace`, `/chat`, `/research`, `/contracts`.

Commit boundary:
1. Shell/nav only.

## P1-03: Capability registry

Goal: one source of truth for tools and command discoverability.

Files:
1. `frontend/lib/capabilities/**` (new)
2. `frontend/components/side-nav.tsx`
3. `frontend/components/chat/CommandPalette.tsx`
4. `frontend/components/chat/CommandSuggestions.tsx`

Implementation steps:
1. Define capability objects (`id`, `label`, `route/action`, `enabled`, `category`).
2. Drive sidebar and command palette from this registry.
3. Add feature-flag style enable/disable support.

Acceptance criteria:
1. Navigation and command systems no longer drift.

Commit boundary:
1. Registry and consumers only.

---

## Phase 2 - Feature Migration into Unified Workspace

## P2-01: Migrate remaining tool pages to workspace-backed panels

Primary targets:
1. `research`
2. `contracts`
3. `search`
4. `ner`
5. `predictions`
6. `compliance`
7. `templates`
8. `clauses`

Implementation steps:
1. Extract each tool into reusable panel components.
2. Keep route wrappers for backwards compatibility.
3. Ensure each panel has standardized states: loading, empty, success, recoverable error.

Acceptance criteria:
1. Users can perform primary workflows without hard page context switching.

## P2-02: Shared context carryover

Goal: tool-to-tool context reuse.

Files:
1. `frontend/lib/context/**` (new or extend existing)
2. workspace panel components

Context objects:
1. Active jurisdiction
2. Active uploaded document text/metadata
3. Current chat thread/conversation ID
4. Selected citations/artifacts

Acceptance criteria:
1. User does not need to repeatedly re-enter same document/jurisdiction.

## P2-03: Legacy share/import parity

Goal: preserve useful `src/app/share/page.tsx` behavior in web stack.

Files:
1. `frontend/app/share/page.tsx` (new if missing)
2. `frontend/lib/conversation-store.ts` and chat components as needed

Implementation steps:
1. Support share payload decode and read-only render.
2. Support import into active conversation with conflict prompt.
3. Keep data size and URL safety constraints explicit.

Acceptance criteria:
1. Share link ingestion and import path works in web app.

---

## Phase 3 - Backend Contract Hardening + Cutover Readiness

## P3-01: Introduce workspace action contract route

Goal: normalize orchestration API for multi-tool workspace execution.

Files:
1. `backend/api/routers/workspace_actions.py` (new)
2. `backend/api/services/workspace_action_service.py` (new)
3. `backend/api/main.py`
4. `backend/tests/test_workspace_actions.py` (new)

Contract target:
1. `POST /api/v1/workspace/actions`
2. Request: `{ action_type, payload, context }`
3. Response: `{ status, data, sources?, citations?, error? }`

Acceptance criteria:
1. At least 5 action types supported through contract.
2. Existing feature routes remain compatible.

## P3-02: Error envelope normalization across routers

Goal: deterministic frontend handling.

Files:
1. `backend/api/routers/**`
2. Shared error helper module (new if needed)

Implementation steps:
1. Standardize non-2xx error schema fields.
2. Replace inconsistent `detail`/raw dict responses.

Acceptance criteria:
1. Frontend can parse errors uniformly.

## P3-03: Security and boundary hardening

Goal: safe handling of HTML-bearing payloads and large inputs.

Tasks:
1. Confirm sanitizer boundaries in backend where applicable.
2. Add request-size/rate-limit strategy documentation.
3. Add tests for malformed payload and unsafe content behavior.

---

## Phase 4 - Remove Legacy `src/` + `src-tauri/` From Mainline

Entry criteria (all required):
1. Phase 0-3 acceptance criteria all green.
2. No production-critical path depends on `src/` or `src-tauri/`.
3. CI is stable on unified stack.

## P4-01: Dependency and runtime detachment audit

Known legacy-coupled files include:
1. `src/lib/tauri-bridge.ts`
2. `src/lib/ml/tauri-ml-bridge.ts`
3. `src/lib/runtime.ts`
4. `src/lib/rag/rag-service.ts`
5. `src/lib/storage/file-storage.ts`
6. `src/components/**` files importing `tauri-bridge`

Tasks:
1. Ensure equivalent web/backend paths exist for required behavior.
2. Mark remaining legacy-only modules as deprecated or delete candidates.

## P4-02: Remove legacy directories

Paths:
1. `src/`
2. `src-tauri/`

Safe removal sequence:
1. Remove imports/references first.
2. Remove scripts that invoke desktop runtime by default.
3. Delete directories only after build/test confirms no dependencies.

Commit strategy:
1. Commit reference cleanup first.
2. Commit directory removals second.
3. Commit package/script cleanup third.

## P4-03: CI + scripts cleanup

Tasks:
1. Make unified web stack default for dev/build/test scripts.
2. Keep optional desktop wrapper scripts only if explicitly required later.

---

## Phase 5 - Later Roadmap: Thin Desktop Wrapper Around Web App

Important: do this only after web stack stabilization.

Principles:
1. Wrapper contains no business/domain logic.
2. Wrapper launches/hosts web UI and delegates all actions to backend.
3. No duplicate command system, no duplicate ML orchestration.

Tasks:
1. Create minimal desktop shell project.
2. Implement launch, session bootstrap, and optional deep-link/file-open bridge.
3. Keep full feature logic in `frontend/` + `backend/` only.

Acceptance criteria:
1. Removing wrapper does not remove product capabilities.
2. Wrapper is distribution-only.

## 7) Feature Parity Audit Backlog (Legacy-to-Unified)

## 7.1 Must-migrate capability categories

1. Chat and branching behavior parity.
2. Command execution parity.
3. Share/import conversation workflow parity.
4. Clause/template/compliance/research functional parity.
5. Settings/jurisdiction persistence parity.

## 7.2 Candidate deprecations (explicit decision needed)

1. Any desktop-only local ML path with no web/backend equivalent usage.
2. Runtime-mode branches used only by legacy desktop UI.
3. Legacy UI components not aligned with workspace architecture.

Decision policy:
1. If capability has active user value and no replacement, migrate.
2. If capability is obsolete or duplicative, deprecate with note in `README2.md` and `docs/`.

## 8) Validation Matrix (Run Per Phase)

## 8.1 Frontend baseline checks

1. `cd frontend && npx tsc --noEmit --pretty false`
2. `cd frontend && npm run lint`
3. `cd frontend && npm run build`

## 8.2 Backend baseline checks

1. `cd backend && pytest -q tests/test_*router.py`
2. Add route-specific tests for changed contracts.

## 8.3 Root-level checks

1. `npm run test:unit`
2. Guardrail script checks for URL payload regressions.

## 8.4 Manual smoke suite

1. Chat send/stream/abort.
2. Command execution for all visible commands.
3. Research with citations and follow-up turn.
4. Contract classify + ToS scan.
5. NER extraction.
6. Prediction runs (all tabs).
7. Templates + clauses render/search.

## 9) Agent Execution Loop (Strict)

For each task ID:
1. Read task definition and owned files.
2. Make smallest possible code change.
3. Run targeted validation.
4. Commit atomically with 5-10 word message.
5. Record progress in this file (optional section below) or docs/audit notes.
6. Proceed to next dependency-unblocked task.

Stop and escalate if:
1. Unexpected unrelated file mutations appear.
2. Required behavior is ambiguous and risky.
3. Validation failures indicate hidden dependency not captured in scope.

## 10) Suggested Immediate Next Queue (Ordered)

1. P0-01 finish `frontend/app/research/page.tsx` migration.
2. P0-02 add CI privacy guardrail script.
3. P0-03 sanitize policy convergence in markdown renderers.
4. P0-04 command parity drift prevention.
5. P1-01 unified API contract module.
6. P1-02 workspace shell route and nav simplification.

## 11) Progress Log Template (Optional)

Use this if the incoming agent wants explicit run logs:

```
- [ ] Task ID:
  - Date:
  - Files:
  - Validation run:
  - Commit hash:
  - Commit message (5-10 words):
  - Notes/Risks:
```

## 12) Documentation Update Policy (Re-stated)

1. Never modify `README.md`.
2. Put README-targeted updates into `README2.md`.
3. Put migration detail and architectural notes under `docs/audit/`.
4. If behavior changes materially, update docs in same PR/commit slice where feasible.

## 13) File-Level Inventories and Required Disposition

## 13.1 Remaining query-param/server-page routes in `frontend/app`

Observed routes still using `searchParams` and/or GET forms:
1. `frontend/app/research/page.tsx` (high risk, text-heavy, mandatory to migrate now).
2. `frontend/app/benchmarks/page.tsx` (medium risk, mostly config text, migrate in Phase 1/2).
3. `frontend/app/rome-statute/page.tsx` (lower risk, short query, optional later standardization).
4. `frontend/app/glossary/page.tsx` (lower risk, search query flow; keep or migrate based on UX strategy).
5. `frontend/app/statutes/page.tsx` (lower risk for text payload, can stay GET if short query only).

Rule:
1. Any form containing large free-form legal text must not remain GET.
2. Short search query forms may remain GET temporarily if allowlisted and documented.

## 13.2 Legacy runtime coupling hotspots (`src/` references)

Primary legacy-coupled modules detected:
1. `src/lib/tauri-bridge.ts`
2. `src/lib/ml/tauri-ml-bridge.ts`
3. `src/lib/runtime.ts`
4. `src/lib/rag/rag-service.ts`
5. `src/lib/storage/file-storage.ts`
6. `src/lib/ai/chat-service.ts`
7. `src/lib/context/JunasContext.tsx`
8. `src/components/chat/MessageInput.tsx`
9. `src/components/settings/ApiKeyModal.tsx`
10. `src/components/ProvidersTab.tsx`
11. `src/components/chat/InlineProviderSelector.tsx`
12. `src/components/chat/ModelProviderStatus.tsx`

Disposition policy:
1. If behavior exists in `frontend/` and is active there, mark legacy module deprecate/delete.
2. If behavior is still unique and user-facing, port to `frontend/` + `backend/` before deletion.
3. Avoid porting runtime abstractions that only exist to support Tauri internals.

## 13.3 Legacy desktop backend (`src-tauri/`) coverage map

Key Rust modules:
1. `src-tauri/src/providers.rs`
2. `src-tauri/src/legal_api.rs`
3. `src-tauri/src/ml.rs`
4. `src-tauri/src/document.rs`
5. `src-tauri/src/vectorstore.rs`
6. `src-tauri/src/tools.rs`
7. `src-tauri/src/keychain.rs`
8. `src-tauri/src/streaming.rs`

Required action:
1. Confirm each module's user-visible behavior is either replaced by FastAPI endpoint or intentionally dropped.
2. Do not delete `src-tauri/` until this confirmation checklist is complete.

## 14) Commit Slicing Blueprint (Strictly Atomic)

Use this as the default commit decomposition model:
1. One task ID can produce multiple commits if touching disjoint concerns.
2. Keep commit scope narrow enough for easy revert.

Suggested immediate sequence:
1. P0-01 commit A: `Migrate research page to client POST flow`
2. P0-01 commit B: `Refine research conversation state and retry UX`
3. P0-02 commit: `Add CI guardrail for large GET payloads`
4. P0-03 commit: `Unify markdown sanitization across chat renderers`
5. P0-04 commit: `Align command palette with handler capabilities`

Commit message hard rules:
1. 5-10 words.
2. Verb-first format recommended.
3. Include scope noun when possible (`research`, `commands`, `CI`, `docs`).

## 15) Validation Runbook by Task Type

## 15.1 Frontend UI/task migration changes

Minimum required:
1. `cd frontend && npx tsc --noEmit --pretty false`
2. `cd frontend && npm run lint`

Recommended before merge:
1. `cd frontend && npm run build`

## 15.2 Backend router/service changes

Minimum required:
1. `cd backend && pytest -q tests/test_*router.py`

When adding new contract route:
1. Add dedicated test module.
2. Run targeted tests for new module plus router baseline.

## 15.3 CI/workflow/script changes

Minimum required:
1. Execute script locally once.
2. Validate script failure mode with temporary intentional violation.
3. Revert test violation and re-run.

## 15.4 Documentation-only changes

Minimum required:
1. Ensure only docs files changed.
2. Confirm no edits to `README.md`.
3. If README-level content changed, verify change is in `README2.md`.

## 16) End-to-End Cutover Checklist

Before declaring `frontend/` + `backend/` full source of truth:
1. Phase 0 tasks complete and verified.
2. Workspace shell available and used as primary surface.
3. Command registry parity checks in place.
4. Action contract route (or equivalent orchestration) in place and tested.
5. No unresolved references from active product paths to `src/` or `src-tauri/`.
6. CI green on agreed required checks.
7. Migration notes and operator guidance updated in `README2.md` and `docs/audit/`.

Before deleting `src/` and `src-tauri/`:
1. Create temporary backup tag/branch marker.
2. Remove references first.
3. Remove directories second.
4. Re-run full validation matrix.
5. Confirm no remaining imports or scripts targeting removed paths.

After deletion:
1. Update architecture docs to remove legacy mentions.
2. Keep a deprecation note in `README2.md` for one release cycle.
3. Begin Phase 5 planning only after stabilization metrics are acceptable.
