# Haus × UiPath AgentHack — Build & Handoff Plan

> **Audience:** the coding agent (Codex) with read/write access to the Haus repository.
> **Purpose:** turn Haus from a single-tool floor-plan editor into a multi-agent, UiPath-orchestrated, design-to-approval-to-handoff solution for **UiPath AgentHack Track 1 (Maestro Case)**, and prepare a winning submission.
> **Status:** planning locked. UiPath Labs access pending. Build order is designed so that an access slip does not block progress.

---

## 0. TL;DR for the coding agent

We are entering **UiPath AgentHack**, a 7-week hackathon ($50,000 in prizes, deadline **30 Jun 2026**). The hackathon's thesis is the gap between a laptop prototype and a *governed, production-grade, orchestrated* agentic system. UiPath must be the orchestration and governance layer.

We are **pivoting Haus** from "furnish a BTO flat" into one deep vertical slice of the home-renovation lifecycle: **intake → multi-agent design generation → compliance check → human approval (UiPath Action Center) → contractor handoff**, with a **dynamic exception/retry loop** at the compliance step. That dynamic loop is the whole reason we qualify for **Track 1 – Maestro Case** rather than Track 2 – BPMN.

**Primary coding agent for the build: OpenAI Codex.** UiPath for Coding Agents supports Codex first-class (alongside Claude Code, Cursor, Gemini CLI) via the UiPath CLI and `uip skills install`. Using a coding agent earns **bonus points** under the Platform Usage criterion, so the build workflow must be captured for the demo video.

**Build order is risk-driven:** build the entire Haus-side multi-agent flow as a **standalone HTTP service first** (works end-to-end with zero UiPath), then wrap it in Maestro Case + Action Center once Labs access lands. If access is late, we still have a working, demoable system.

Read sections 1–3 for context, **4 for the architecture**, **5 for the staged build plan (your actual work)**, 6 for open investigation tasks, and 7 for submission prep. **Before reading further, scan §0.1 for what already landed.**

---

## 0.1. Progress (as of 2026-06-09)

What has been done since the plan was written. Cross-references to artifacts.

### Landed
- **LICENSE.** MIT, copyright "Gabriel Ong", at repo root. `pyproject.toml` carries `license = {text = "MIT"}` + MIT classifier.
- **Demo fixture pinned.** `tests/fixtures/bto_3room_orange.jpg` + `corpus/library/3.json` (113 walls, 15 structural + 3 shelter + 10 partition + 85 ferrolite; 5 rooms). Money-shot target: `wall_28` (shelter, geo `[2.3226, 2.6, 0.3]`, color 7874600). Backup: `wall_82`. Fallback: doorway block. Pin recorded in `SPEC-HTTP-CASE.md` §1 + a pointer in `README.md`.
- **Stage 1 contract (`SPEC-HTTP-CASE.md` at repo root).** Locks: case payload schema (extends `corpus/library/*.json` shape with `case_id`, `case_schema_version`, `design_status` enum, `revise_count`, `compliance_findings[]` with `machine_hint`, `approval_state`, `vendor_handoff`, reserved keys `pinned_proposal_id` + `vendor_cache_key`); 5 HTTP endpoints with state transitions; revise-loop policy (N=3 default); two compliance rules (`structural_wall_protected`, `walkway_accessibility`); the `hdb_type` propagation gap as a callout prerequisite; Appendix A 10-step round-trip.
- **`hdb_type` enrichment + raster propagation.** `src/haus/case/ingest.py` inverts `mesh._COLOR_BY_HDB` so older library Cases carry explicit `hdb_type`; `src/haus/mesh.py` / `src/haus/pipeline.py` now emit `hdb_type` directly for newly vectorized raster layouts.
- **Compliance Agent v0** (`src/haus/case/compliance.py`). Two rules emitting SPEC §2.4 findings: `structural_wall_protected` (diffs current items[] vs baseline snapshot; v0 detects removal only — move/resize deferred), `walkway_accessibility` (adjacent-room pairs from `rooms[].bounds`, corridor sampling; reuses private polygon helpers from `mcp_server`).
- **Design Agent v0** (`src/haus/case/design_agent.py`). Pinned-proposal path (deep-copy items from `{proposal_id}.json` in a proposals dir) + deterministic fallback (`agent_loop.plan_room` + `mcp_server._build_furniture_item`). Live LLM proposal generation is wired as explicit opt-in with deterministic fallback; pinned proposals remain the recorded-demo path.
- **Revise loop + N-failure escalation** (`src/haus/case/revise_loop.py`). `step_design`/`step_compliance`/`step_revise`/`patch_approval` matching the SPEC §4 endpoint surface; `ReviseLoop` orchestrator; `run_to_human` driver. `InvalidStateTransition` enforces pre-states.
- **Stage 1 HTTP service** (`src/haus/case/http_server.py`). Starlette/Uvicorn wrapper over the case step functions: `POST /case`, `POST /case/{id}/design`, `POST /case/{id}/compliance`, `POST /case/{id}/revise`, `GET /case/{id}`, plus the temporary `PATCH /case/{id}/approval` Stage-1 approval stub. CLI entrypoint: `haus case-server`.
- **Vendor/Handoff Agent v0** (`src/haus/case/vendor_handoff.py`). Cache-first vendor resolver with deterministic live-search stub fallback; generates a per-case `packet.zip` containing `handoff.json` + `summary.md`, populates `vendor_handoff`, and transitions `approved -> handoff_complete`. Demo cache lives at `tests/fixtures/vendors/demo_hdb_renovation.json`; HTTP route: `POST /case/{id}/handoff`.
- **Three.js Case Review wiring.** Editor now accepts Case JSON via `?case=...` or JSON import, renders current `items[]`, overlays baseline ghosts from `_baseline_items`, highlights compliance findings, and exposes a compact Case Review panel. `haus view --case <case.json>` opens this path.
- **Raster `hdb_type` propagation.** `src/haus/mesh.py:floor_plan_to_layout` serializes raster-extracted walls into layout items with explicit `hdb_type`/`wall_type` fields; `src/haus/pipeline.py` writes `layout.json` beside `model.glb`; MCP/editor JSON round-trips preserve these fields.
- **Hero demo CLI flow.** `haus case demo --fixture corpus/library/3.json --pinned demo_3room_remove_wall_28` drives the lifecycle through the Stage-1 HTTP app, prints transition lines, writes a final Case JSON, and completes approval + handoff by default.
- **DesignAgent live mode is opt-in.** Default remains pinned/deterministic for recorded-demo reliability. `--design-mode live` / `HAUS_CASE_DESIGN_MODE=live` enables structured live LLM proposals with deterministic fallback and optional cache writing.
- **Demo pinned proposals.** `tests/fixtures/proposals/demo_3room_remove_wall_28.json` (money-shot: removes wall_28 → triggers `structural_wall_protected` every revise → N escalation) and `demo_3room_keep_walls.json` (clean path → goes straight to `awaiting_human_approval` with no escalation_reason).
- **Guided Room Capture.** Editor accepts room reference photos plus width/depth/height/opening measurements, calls `/api/room-capture/layout`, and builds an editable measured room shell with photo reference panels. This is guided reconstruction, not photogrammetry.
- **IKEA catalog search.** Editor, HTTP, chat, and MCP surfaces can search/place IKEA catalog items. TinyFish is used when `TINYFISH_API_KEY` is set; local cache/seed items keep the UI usable offline.
- **Tests.** Case/backend/CLI/browser coverage now includes baseline Case snapshots, raster layout `hdb_type`, live-mode fallback, the hero demo CLI, and Case Review panel loading. Full repo suite passes locally; Ruff and Pyright are clean.

### Honest scoping notes (read these before continuing)
- **HTTP server exists.** The Stage-1 Starlette/Uvicorn layer now wraps the case lifecycle and can run with `haus case-server`. It is intentionally local/single-tenant with process-local storage; persistence/auth/concurrency are still deferred.
- **Vendor agent is cache-backed only.** The v0 handoff agent has a deterministic live-search stub fallback, but no TinyFish/Serper implementation yet. IKEA catalog search is separate and does use TinyFish when configured.
- **Live LLM is opt-in, not the recorded-demo default.** The Design Agent has pinned replay, deterministic fallback, and explicit live provider mode. The recorded demo should still rely on pinned proposals for reliability.
- **Three.js Case Review is demo-focused.** It renders baseline/current diff and finding highlights, not a full Action Center replacement. Stage 2 still needs real Action Center wiring.
- **Raster layout serialization now emits `hdb_type`.** Existing `corpus/library/{1..4}.json` remain supported through ingest-time color inversion; newly vectorized `layout.json` files carry explicit fields.

---

## 1. The hackathon problem (context)

**UiPath AgentHack** asks builders to ship a *real, working* agentic solution — not a slide deck — that runs on the **UiPath Platform** as the orchestration and governance layer. The core challenge framed by the organizers: it is easy to spin up an AI agent on a laptop; it is hard to make agents *operate and govern at scale* — handle complexity, survive interruptions, keep humans in the loop, and run in production.

There are three tracks. We are doing **Track 1 — UiPath Maestro Case**:

> Build a solution that orchestrates dynamic, exception-heavy business processes using UiPath case management. Work moves through stages, with handoffs between agents, robots, and people, and humans stay in charge at key decision points.

The organizers' own tiebreaker decides our track for us:
> *"If your process has unpredictable paths that emerge as the work unfolds, choose Track 1 – Maestro Case. If your process has a predictable sequence you can map in advance, choose Track 2 – BPMN."*

Our flow is **unpredictable by design**: the number of design→compliance→revise loops is not known in advance, and whether a case escalates to a human depends on what the agents find. That emergent shape is exactly what Maestro Case is for. (Confirmed against UiPath's own materials: Maestro Case treats each case as a living entity with its own timeline and participants, a case-manager agent governing the lifecycle, and stage-manager agents driving phases — with ambiguous items escalated to human review. UiPath's flagship example is insurance claims: AI validates, straightforward cases auto-process, ambiguous ones escalate. Our design→compliance→escalate loop is structurally the same pattern.)

**What must be submitted (all four required):**
1. A Devpost project page (title, **track selection**, written description, business problem, how it works, screenshots).
2. A **demo video, max 5 minutes**, on YouTube/Vimeo/Youku, showing the solution *running* (not slides), walking the architecture, naming the agents and how they're orchestrated, and showing where humans fit.
3. A **public GitHub repo** (MIT or Apache 2.0) with a README covering what it does, which UiPath components it uses, setup, prerequisites, and whether it uses coding agents / low-code agents / a combination.
4. A solution **built on UiPath Automation Cloud** — orchestration and agent logic running through the UiPath Platform.
   - Plus a **presentation deck** (template provided by organizers).
   - Optional **product-feedback form** → eligible for the Best Product Feedback award ($1,500).

**Judging criteria:** Business Impact & Adoption Potential · Platform Usage (depth/deliberateness of UiPath use) · Technical Execution, Feasibility & Versatility (incl. exception/failure/edge-case handling) · Completeness of Delivery · Creativity & Innovation · Presentation. **Bonus points** for demonstrating coding agents through UiPath for Coding Agents, within the Platform Usage criterion, in both judging phases.

---

## 2. Why Haus, why this pivot (decision record)

We evaluated two existing repos: **Swee SG** (a governance/audit/policy layer over public-data tool calls) and **Haus** (this repo — Python + Three.js for HDB/BTO floor plans). Swee is arguably the *more native* fit because its Shield component already embodies policy/audit/escalation. We chose **Haus anyway**, deliberately, with eyes open to the trade:

- **Why Haus:** it is the far stronger *visual* demo (Three.js editor, GLB geometry), which helps disproportionately on Presentation, Creativity, and the side prizes (Most Creative $3k, Best Demo $3k, Best Cross-Platform Integration $1.5k).
- **The risk we are accepting:** furnishing-only Haus has a thin enterprise business case. We fix that by **expanding scope to the renovation lifecycle** so the flow becomes genuinely exception-heavy and handoff-driven (real Track 1 material).
- **The risk that expansion creates (watch this):** most of a full lifecycle (intake, vendor lookup, scheduling) is *generic orchestration* that does not showcase Haus's unique IP (vectorization → GLB geometry → spatial scoring). If the demo spends its minutes on intake forms and vendor lookups, we demote our differentiator and become "a thin UiPath layer over a fat non-UiPath app," which hurts Platform Usage.
- **Mitigation (the core design decision):** **do not build the whole lifecycle.** Build *one deep vertical slice* — design-to-approval-to-handoff — that puts Haus's geometry/compliance capability at the **center**, with the contractor/vendor layer kept deliberately **thin** (just enough to prove the handoff exists). Gesture at the broader lifecycle; build one loop deeply.

**Net:** Haus is viable for Track 1 because of the lifecycle reframing, and competitive on the visual criteria, *provided* the design+compliance loop stays the star of the demo.

---

## 3. Confirmed assumptions & answers (carried forward)

These were settled in planning and are inputs to the build:

1. **UiPath Labs access:** not provisioned yet; expected soon. **Top schedule risk.**
2. **UiPath familiarity:** cold start. No Maestro / Agent Builder / Action Center experience. Week 1 must include platform learning + spike work.
3. **Maestro external execution:** open investigation (see §6, task A). First spike: can Maestro call external HTTP cleanly; should Haus run as HTTP service / CLI wrapper / Python node.
4. **Haus pipeline runtime:** demo-feasible. `haus build` on a sample BTO fixture ran ~1.6s wall time locally. Treat known demo inputs as **inline-capable**; use async/callback only if UiPath adds latency/remote constraints.
5. **Multi-agent today:** does not exist yet. Current `agent_loop.py` is **deterministic kit-based planning** exposed via MCP tools like `design_room` / `design_flat`.
6. **Agent pattern for the demo:** LLM-driven agents on top, **Haus deterministic underneath.** Pattern: LLM planner proposes intent → Haus tools execute/validate → compliance agent checks → human approves.
7. **HDB renovation compliance:** not encoded today. Existing code has HDB **wall classification**, sightline checks, doorway accessibility, walkway scoring — but **no renovation ruleset**.
8. **Best demo failure (the money-shot):** LLM proposes removing/modifying a structural/shelter wall → compliance agent **blocks** and escalates to Action Center. **Backup failure:** furniture blocks a doorway/walkway → existing accessibility scoring triggers.
9. **Human reviewer framing:** **internal renovation coordinator/designer** approving before contractor handoff (enterprise framing — stronger adoption story than a homeowner approving their own flat). *(This was an open call; see §6 task D to finalize wording, but build to the coordinator framing.)*
10. **Approval surface:** **UiPath Action Center** (not a parallel approval inside Three.js) — better Platform Usage signal.
11. **Contractor handoff:** real-ish via live vendor search (TinyFish / Serper) where available; **cache selected vendors** into a simple directory after discovery. Do **not** depend on guaranteed "contact IDs" from live search.
12. **Demo assets exist:** `corpus/cleaned/*.jpg`, `tests/fixtures/*.jpg`, prebuilt layouts in `corpus/library/*.json`.
13. **Team:** one human + coding agents. Split agents by workstream: UiPath spike · Haus HTTP/MCP wrapper · compliance rules · Three.js/demo polish · test/video script.
14. **Three.js editor:** reuse it in the demo. Strongest visual proof — UiPath orchestrates, Haus generates/validates, Action Center approves, editor shows before/after layout.
15. **Coding agent:** **OpenAI Codex** is the primary build agent.

---

## 4. Target architecture (Track 1 — Maestro Case)

### 4.1 The case lifecycle (the unit of work)

A **"Renovation Design Case"** is the living entity that moves through Maestro Case stages. Proposed stages:

```
INTAKE → DESIGN → COMPLIANCE → (revise loop) → HUMAN_APPROVAL → CONTRACTOR_HANDOFF → CLOSED
                       ^                              |
                       └──────── auto-revise ─────────┘
                       (after N failures → escalate to HUMAN_APPROVAL as a block decision)
```

The **dynamic** part — and the Track 1 justification — is the COMPLIANCE→DESIGN revise loop plus the conditional escalation. Path emerges as work unfolds.

### 4.2 Agents (multi-agent decomposition)

| Agent | Role | Built with | Notes |
|---|---|---|---|
| **Case Manager** | Governs case lifecycle, stage transitions, retry counting, escalation decision | Maestro Case (native) | The orchestrator; owns the loop and the N-failure escalation rule |
| **Intake Agent** | Structures the brief: floor-plan ID, requirements, constraints | LLM (Agent Builder or external) | Thin; produces the initial case payload |
| **Design Agent** | LLM planner proposes layout *intent*; calls Haus deterministic tools to execute/validate | LLM planner + Haus tools (`design_room`/`design_flat`, object CRUD) | **This is the star.** LLM proposes; Haus executes deterministically underneath |
| **Compliance Agent** | Checks proposed design against renovation ruleset; emits structured violation findings | Haus rules + LLM framing | Source of the demo failure; see §4.4 |
| **Vendor/Handoff Agent** | Matches design to vendors; produces handoff package | Thin; live search (TinyFish/Serper) with cached fallback | Deliberately thin — proves handoff exists, not a full CRM |
| **Human reviewer** | Internal renovation coordinator approves/rejects in Action Center | UiPath Action Center | The human-in-the-loop decision point |

> External-framework note: the hackathon *encourages* external frameworks (LangChain/CrewAI/AutoGen) as long as UiPath orchestrates. We can build the Design/Compliance agents as external-framework agents and let Maestro coordinate them — this strengthens the "blend UiPath-native + external agents" story the organizers explicitly reward.

### 4.3 Haus stays the differentiator

The LLM agents sit *on top*. Underneath, the value is Haus-native and deterministic: raster→vector→GLB geometry, wall classification, sightlines, doorway/walkway accessibility, placement simulation. The demo must make the **design generation + compliance loop** the visible centerpiece, with the Three.js editor showing **before/after** layouts.

### 4.4 The compliance loop (critical path — see §6)

When the Compliance Agent blocks a design, it emits **structured violation findings** (machine-readable: rule id, severity, offending element id/coords, human-readable reason). The Case Manager then either:
- routes findings **back to the Design Agent** for an automated revise attempt (primary path — best "agents handle exceptions" story), or
- after **N failed attempts**, escalates to **Action Center** for the human coordinator to decide (block / override / send back).

This dual routing (auto-revise primary, human escalation after N) is what demonstrates *both* autonomous exception handling *and* humans-in-charge — directly hitting the Technical Execution and "keep humans in the loop" criteria.

---

## 5. Staged build plan (the work)

**Guiding principle:** de-risk the UiPath dependency. Build the Haus-side system so completely that UiPath becomes a genuine-but-thin orchestration wrapper over a system that already works end-to-end. **Stages 1–3 require no UiPath access.**

### Stage 0 — Foundations & investigation (Week 1, parallel with access wait)
- [ ] **Spike A (highest priority):** verify Maestro can call external HTTP cleanly; decide Haus packaging (HTTP service vs CLI wrapper vs Python node). See §6 task A. *Do this the moment Labs access lands; until then, design the HTTP contract so it's orchestration-agnostic.* — **BLOCKED on Labs access.**
- [ ] Install UiPath CLI + Codex skills: `uip skills install --agent codex` (verify exact invocation against current UiPath CLI docs). Confirm Codex recognizes UiPath tasks (`uip solution pack/publish/deploy`). — **BLOCKED on Labs access.**
- [x] Inventory the repo: confirm the current state of `extraction.py` wall classification (see §6 task B — this gates the compliance critical path). — **Resolved:** classification already exists at `src/haus/extraction.py:386` (`_snap_to_hdb`) and `:396` (`_classify_wall_hdb`); persisted on `WallSegment.hdb_type` at `src/haus/types.py:32`. See §0.1 + §6 B.
- [x] Pick and pin the **demo floor-plan fixture** from `corpus/cleaned/` or `tests/fixtures/`. Verify `haus build` runs clean and fast on it. — **Pinned:** `tests/fixtures/bto_3room_orange.jpg` + `corpus/library/3.json`; recorded in `SPEC-HTTP-CASE.md` §1.
- [x] Choose LICENSE: **MIT or Apache 2.0** (hackathon requires one). Add it now. — **MIT added** (`LICENSE` at repo root; `pyproject.toml` updated).

### Stage 1 — Haus-side multi-agent flow as a standalone HTTP service (Weeks 1–3, no UiPath needed)
Build the entire flow as an HTTP service so it works end-to-end before any orchestration exists.
- [x] Define and expose the **HTTP service contract** (the orchestration boundary). Endpoints: `POST /case` (create from floor-plan + brief), `POST /case/{id}/design` (run Design Agent), `POST /case/{id}/compliance` (run checks → findings), `POST /case/{id}/revise` (auto-revise from findings), `GET /case/{id}` (state), plus the Stage-1-only approval stub. — **Contract frozen** in `SPEC-HTTP-CASE.md` §4; Starlette/Uvicorn implementation landed at `src/haus/case/http_server.py`.
- [x] Define the **Renovation Design Case payload schema** (see §6 task C — reuse the existing viewer JSON `{version, metadata, rooms, items}` as the base, extended with `design_status`, `compliance_findings[]`, `approval_state`, `revise_count`). — **Done:** `SPEC-HTTP-CASE.md` §2; full canonical example in §2.9.
- [x] Implement **Design Agent**: LLM planner → Haus tools. Make the LLM proposal **pinnable/cacheable** for deterministic demo replay (see §6 task F). — **v0 done:** `src/haus/case/design_agent.py` (pinned + deterministic-fallback paths; explicit live provider mode with fallback). Pinned proposals carry the recorded demo.
- [x] Implement **Compliance Agent** with a **deliberately scoped ruleset** (see §6 task B): structural-wall-removal block + doorway/walkway accessibility. Frame as "extensible ruleset, demonstrated on structural integrity + accessibility." Emit structured findings. — **v0 done:** `src/haus/case/compliance.py`; two rules; findings carry `machine_hint`. *`structural_wall_protected` detects removal only in v0 (SPEC §5.1 lists move/resize; not implemented).*
- [x] Implement the **revise loop** logic (auto-revise from findings; N-failure threshold; then mark for escalation). — **Done:** `src/haus/case/revise_loop.py`; N=3 default; SPEC Appendix A round-trip passes as an integration test.
- [x] Implement **Vendor/Handoff Agent** (thin): live search where available, **pre-seeded cache** for the demo (see §6 task E). — **v0 done:** `src/haus/case/vendor_handoff.py`; pre-seeded cache at `tests/fixtures/vendors/demo_hdb_renovation.json`; HTTP route `POST /case/{id}/handoff`; writes `packet.zip` and populates `vendor_handoff`.
- [x] **Acceptance for Stage 1:** the full loop runs from the CLI/HTTP with zero UiPath, producing the money-shot structural-wall failure → auto-revise attempts → human escalation/approval → handoff package, and the Three.js editor renders Case before/after. — **Done:** `haus case demo` drives the HTTP app through the recorded-demo path; clean pinned proposal covers the straight-to-approval path; editor Case Review renders baseline/current diff and finding highlights.

### Stage 2 — UiPath orchestration wrap (Weeks 3–5, requires Labs access)
- [ ] Model the case in **Maestro Case**: stages from §4.1, Case Manager governs transitions + retry counting + escalation rule.
- [ ] Wire each stage to call the Haus HTTP service (per Spike A's verdict).
- [ ] Implement the **Action Center** human-approval task for the coordinator (block/override/send-back), wired to the escalation branch.
- [ ] Decide which agents are **Agent Builder (native)** vs **external framework** and document the split (the README must state coding vs low-code vs combination).
- [ ] **Acceptance for Stage 2:** the same loop now runs *orchestrated by Maestro*, with the human approval happening in Action Center, fully on UiPath Automation Cloud.

### Stage 3 — Coding-agents bonus, polish, hardening (Weeks 4–6)
- [ ] Capture **Codex driving the UiPath build** on camera for the bonus (the `uip` pack/publish/deploy flow through Codex). This is free Platform-Usage points — do not skip.
- [ ] Exception/edge-case hardening for the demo: what happens on a malformed plan, a vendor-search miss (falls back to cache), an LLM timeout (falls back to pinned proposal). Judges explicitly score exception handling.
- [ ] Three.js editor polish: clean before/after, highlight the violating wall/element, show the approved result.

### Stage 4 — Submission assembly (Week 6–7, see §7)
- [ ] Devpost page, demo video (≤5 min), README, deck, optional feedback form.

---

## 6. Open investigation tasks (frame these to Codex, repo-aware)

These are the questions that still need answers from the codebase or the platform. Ordered by criticality.

**A. Maestro external execution (platform spike).** Verify whether UiPath Maestro can call external HTTP services cleanly, and determine whether Haus should run as an HTTP service, a CLI wrapper, or a Python node. What is the smallest test that confirms this? *Blocks Stage 2 wiring.* — **OPEN. Blocked on Labs access.**

**B. Wall classification — does it already separate structural from partition? (gates compliance critical path).** In the current `extraction.py` output, does the HDB wall classifier distinguish structural/load-bearing/shelter walls from non-structural partition walls, or label all walls generically? Show where wall class is assigned. *If it already distinguishes them, the money-shot failure is nearly free. If not, building that distinction is the Compliance Agent's first job and the top critical-path item.* — **RESOLVED.** Classification exists at `src/haus/extraction.py:386` (`_snap_to_hdb` returns `ferrolite|partition|structural|shelter`) and `:396` (`_classify_wall_hdb` enriches each `WallSegment`); persisted on `WallSegment.hdb_type` at `src/haus/types.py:32`. Library-side enrichment landed at `src/haus/case/ingest.py:_HDB_BY_COLOR`; raster-side propagation now lands through `src/haus/mesh.py:floor_plan_to_layout` and `src/haus/pipeline.py` writing `layout.json`.

**C. Case payload schema.** Can we reuse the existing viewer JSON (`version`, `metadata`, `rooms`, `items` with `type/pos/rot/geo/color`/names/room tags) as the Renovation Design Case payload, extended with `design_status`, `compliance_findings[]`, `approval_state`, `revise_count`? Propose the exact schema and where it's defined. — **RESOLVED.** Base shape is `corpus/library/*.json` (not the minimal viewer JSON — Design Agent needs `rooms[]`, Compliance needs `metadata.scale_m_per_px`). Full schema in `SPEC-HTTP-CASE.md` §2 (top-level keys §2.2, `design_status` enum §2.3, `compliance_findings[]` shape §2.4, `approval_state` §2.5, canonical example §2.9). Implementation: `src/haus/case/ingest.py:load_case_from_library`.

**D. Structured violation findings + retry routing.** When the Compliance Agent blocks a design, what exactly goes back on the loop? Target: design → compliance fail → **auto-revise by the LLM planner using structured findings** → re-check → after **N** failures → escalate to a human in Action Center. Define the findings structure (rule id, severity, offending element id/coords, reason) so the planner can act on it programmatically, and set the default **N**. — **RESOLVED.** Findings shape in SPEC §2.4 (load-bearing field is `machine_hint`, a structured object the planner consumes programmatically — *not* the natural-language `reason`). Default `N = 3` (SPEC §4.4; demo may override to `N=1`). Replay contract: SPEC §5.3 (the output of `/compliance` must be valid as the `findings` input of `/revise`). Implementation: `src/haus/case/compliance.py` + `src/haus/case/revise_loop.py`. Tested end-to-end via `tests/test_case_revise_loop.py::test_appendix_a_round_trip`.

**E. Vendor cache for a reliable demo.** For the *recorded* demo, pre-seed the vendor cache so the contractor-handoff step never depends on a live TinyFish/Serper call. Where does the cache live, what's its schema, and how does the handoff agent read from it (cache-first, live-search-fallback)? — **RESOLVED.** Cache directory: `tests/fixtures/vendors/` for demo fixtures, configurable through `HAUS_VENDOR_CACHE_DIR` / `--vendor-cache-dir`; default cache key: `demo_hdb_renovation`; schema: `{cache_key, description, retrieved_at, vendors: [{vendor_id, vendor_name, specialties, service_area, contact, packet_template}]}`. Implementation: `src/haus/case/vendor_handoff.py`; reads cache-first and falls back to a deterministic live-search stub for v0; writes `packet.zip` and sets `vendor_handoff`.

**F. Deterministic LLM replay.** Pin/cache the Design Agent's LLM proposal for the demo run so the 5-minute video is deterministic and replayable, while keeping live generation as the real capability. How do we store and replay a pinned proposal (keyed by floor-plan fixture + brief)? — **RESOLVED.** Contract surface reserved in SPEC §2.8 (`pinned_proposal_id`) and §6. v0 storage = `{proposal_id}.json` files in a configurable proposals directory; payload = `{proposal_id, description, items[]}` (full replacement); deep-copied on load to avoid disk-state corruption. Demo proposals shipped at `tests/fixtures/proposals/demo_3room_remove_wall_28.json` (money-shot) and `demo_3room_keep_walls.json` (clean path). Live provider calls are opt-in (`--design-mode live` / `HAUS_CASE_DESIGN_MODE=live`) and fall back deterministically if credentials, provider calls, or structured output fail. Recorded demo recommendation remains pinned-only.

**G. Coordinator framing wording.** Finalize the human-reviewer persona as an **internal renovation coordinator/designer** approving before contractor handoff. Confirm what this changes in the approval payload (what the coordinator sees: before/after render, violation findings, vendor options) and in the demo narration. — **PARTIAL.** SPEC §2.5 defines `approval_state` (with `reviewer`, `escalation_reason`); SPEC §4.4 defines the Stage-1 PATCH stub for the human transition. The editor now provides before/after diff + finding overlay; final narration/persona wording and real Action Center task copy still need Stage-2 work.

**H. UiPath CLI + Codex setup.** Confirm the exact `uip skills install` invocation for Codex against current UiPath CLI docs, and that Codex resolves UiPath tasks. (Build order: Stage 0.) — **OPEN. Blocked on Labs access.**

---

## 7. Submission preparation (map to deliverables & criteria)

### 7.1 The four required artifacts
1. **Devpost project page** — title; **Track 1 – UiPath Maestro Case** clearly selected; description of the design-to-approval-to-handoff solution; the business problem (AI-assisted renovation design with compliance gating + governed contractor handoff for an internal renovation/ID firm); how it works; screenshots (before/after editor, Action Center approval, the violation block).
2. **Demo video (≤5 min)** — see script guidance below. Must show it *running*, walk the architecture, name the agents + orchestration, show the human's role.
3. **Public GitHub repo (MIT/Apache 2.0)** — README: what it does · UiPath components used (Maestro Case, Action Center, Agent Builder/external split) · setup · prerequisites · **explicit statement: combination of coding agents (Codex) + agents**. Setup must be reproducible enough that another dev could run it.
4. **On UiPath Automation Cloud** — orchestration + agent logic through the platform; README lists all UiPath components; video shows it running on the platform.
   - **Deck** (organizers' template) — upload to Drive/OneDrive/Dropbox, share-all permissions.
   - **Optional feedback form** — fill it; eligible for Best Product Feedback ($1,500). Low effort, real upside given we're a cold-start team with genuine first-impressions feedback.

### 7.2 Demo video script (5-minute budget — protect the differentiator)
Keep the **design + compliance loop** as the star. Suggested beats:
- **0:00–0:30** Problem: renovation firms drown in design iterations + manual HDB compliance checks; AI proposes, but who governs it?
- **0:30–1:00** Architecture: one-screen diagram — Maestro Case orchestrates Intake → Design → Compliance → Approval → Handoff; agents named.
- **1:00–3:00** **The money shot (longest segment):** live run. LLM Design Agent proposes a layout (Three.js before). Compliance Agent **blocks** the structural-wall removal with a clear finding. Auto-revise loop fixes it. Three.js after.
- **3:00–4:00** Human-in-the-loop: coordinator approves in **Action Center**; then contractor **handoff package** produced.
- **4:00–4:40** **Bonus:** show **Codex** building/deploying part of this through UiPath for Coding Agents (`uip` flow).
- **4:40–5:00** Impact + close.

### 7.3 Criteria coverage checklist
- [ ] **Business Impact** — internal renovation/ID firm framing; clear adoption story; scalable.
- [ ] **Platform Usage** — Maestro Case + Action Center + Agent Builder/external split, *deliberate* not incidental; **Codex bonus captured on camera.**
- [ ] **Technical Execution** — exception handling visible (revise loop, vendor miss → cache, LLM timeout → pinned proposal); structural soundness.
- [ ] **Completeness** — functional end-to-end prototype + public repo w/ README + setup + ≤5 min video.
- [ ] **Creativity** — spatial multi-agent design + governed compliance loop is an unexpected orchestration pattern.
- [ ] **Presentation** — tight problem→solution→impact arc; the loop demoed live and confidently.

### 7.4 Side prizes worth targeting (cheap upside)
- Best Cross-Platform Integration ($1,500) — Three.js + Python + UiPath + external vendor search is a real cross-platform story.
- Most Creative Solution ($3,000) / Best Demo ($3,000) — our visual strength.
- Best First-Time Builder ($1,500) — we're a cold-start team; mention it.
- Best Product Feedback ($1,500) — fill the form.

---

## 8. Risks & mitigations (keep visible)

| Risk | Why it matters | Mitigation |
|---|---|---|
| **UiPath access slip + cold start** | ~3 weeks runway; UiPath is non-negotiable for the rules; a 1-week slip costs a third of runway on the one mandatory component | **Build order:** Stages 1–3 need no UiPath. The Haus HTTP service works end-to-end first; UiPath becomes a thin wrap. An access slip degrades scope, not viability. |
| **Compliance ruleset doesn't exist yet** | The money-shot demo failure depends on code not yet written; §6 task B decides if it's a 1-day or 1-week job | Hard-scope the ruleset to exactly the two failure scenarios; frame as "extensible." Resolve task B first. |
| **"Haus is just one node"** | If the demo emphasizes intake/vendor lookups, we demote our unique IP and weaken Platform Usage | Keep design+compliance loop the star (video budget §7.2); keep vendor agent thin. |
| **Live demo fragility** | A failed vendor search or LLM timeout mid-recording is an unforced error | Pre-seed vendor cache (task E) + pin LLM proposal (task F); show fallbacks *as* exception handling. |
| **Scope creep ("handle everything")** | Trying to build the whole lifecycle in 3 weeks → shallow everywhere → reads as a slide deck | Build ONE deep slice. Gesture at the rest. |

---

## 9. Immediate next actions

Ordered by criticality given Stage-1 progress in §0.1. Items 1–5 do not require Labs access.

1. **Codex:** build the **HTTP service layer** that wraps the four step functions already implemented in `src/haus/case/`. — **Done.** Starlette/Uvicorn service lives at `src/haus/case/http_server.py`; CLI entrypoint is `haus case-server`.

2. **Codex:** **Vendor/Handoff Agent v0** (§5 Stage 1 last open item; §6 task E). — **Done.** Cached vendor directory (`tests/fixtures/vendors/` or `~/.haus/vendors/`); schema `{vendor_id, vendor_name, packet_template, ...}`; handoff agent reads cache-first, with live-search (TinyFish/Serper) as a stubbed fallback for v0. Wires into `vendor_handoff` on the Case + a new `handoff_complete` transition. Keep deliberately thin — see §2 "watch this" — the goal is to prove the handoff exists, not build a CRM.

3. **Codex:** **wire the Three.js editor to render Case before/after** (§5 Stage 1 acceptance, item c; §6 task G). — **Done.** The editor reads Case payloads via `?case=...` or JSON import, renders current `items[]`, overlays baseline ghosts from `_baseline_items`, highlights findings, and shows a Case Review panel.

4. **Codex:** **finish the `hdb_type` propagation gap on the raster path** (SPEC §3 callout). — **Done.** `floor_plan_to_layout` emits explicit wall classification into raster-generated `layout.json`; MCP/editor JSON paths preserve the fields.

5. **Codex:** **hero demo CLI flow.** — **Done.** `haus case demo --fixture corpus/library/3.json --pinned demo_3room_remove_wall_28` runs through the Stage-1 HTTP app, prints transition lines, writes Case JSON, approves, and completes handoff unless skipped.

6. **Codex (decision needed before recording):** wire a **real LLM provider call** into `DesignAgent` (§6 task F still-open). — **Done with decision.** Recorded demo should stay pinned-only for reliability; live LLM proposal generation is exposed as opt-in `--design-mode live` / `HAUS_CASE_DESIGN_MODE=live` with deterministic fallback and optional proposal caching.

7. **Human:** the moment UiPath Labs access lands, run **Spike A** (§6 A) and `uip skills install --agent codex` (§6 H). These unblock §5 Stage 2.

8. **Human:** product feedback form (§7.1, Best Product Feedback $1.5k). 30-minute task; do it once Stage 1 is HTTP-exposed and you have real first-impressions opinions on Maestro/Action Center post-Stage-2.

9. Keep the **design + compliance loop** as the demo's centre of gravity in every decision (§2 mitigation; §7.2 video budget).
