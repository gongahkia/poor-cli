# SPEC-HTTP-CASE — Stage 1: Standalone HTTP service for the Renovation Design Case

> **Status:** Locked. Stage 1 (pre-Maestro) contract for the UiPath AgentHack pivot of `Haus`. See [`TODO-9JUNE-START.md`](./TODO-9JUNE-START.md) for strategic context.
> **Audience:** the agent(s) implementing the HTTP service, the Compliance Agent, the Design Agent wrapper, the revise loop, the demo video script, and (later) Stage 2 Maestro Case wiring.
> **Source of truth:** when this document and an implementation disagree, this document wins until amended here.

---

## 0. Status, scope, non-goals

**In scope:**
- The HTTP service contract (5 endpoints) that Stage 2 Maestro Case will wrap.
- The "Renovation Design Case" payload schema — extends the existing `corpus/library/*.json` shape.
- Two compliance rules (`structural_wall_protected`, `doorway_accessibility`).
- The demo fixture pin (one image, one layout, one target wall, one fallback failure).
- Reserved keys for demo-determinism subsystems (LLM replay, vendor cache) — *contracts only*, not designs.

**Out of scope (deferred; see §7 for the full list):** code · Maestro Case / BPMN mapping · Action Center wire format · multi-tenancy · rate limiting · external DB/identity integration · additional compliance rules.

**Operating principle:** the Stage-1 HTTP service must work end-to-end *without any UiPath component*. Stage 2 will wrap it as a thin orchestration layer. If a Stage-1 detail forces a Stage-2 dependency, it is wrong.

---

## 1. Demo fixture pin

The fixture is pinned here as the **single source of truth**. The HTTP service config, the demo video script, the test harness, and any narration must read these values from this section (or copy verbatim — not redefine).

| Key | Value |
|---|---|
| `fixture_image` | `tests/fixtures/bto_3room_orange.jpg` |
| `fixture_layout` | `corpus/library/3.json` |
| `target_wall_primary` | `wall_28` — geo `[2.3226, 2.6, 0.3]`, color `7874600` (shelter encoding) |
| `target_wall_backup` | `wall_82` — geo `[4.8387, 2.6, 0.3]`, color `7874600` (shelter encoding) |
| `fallback_failure_mode` | Place a `wardrobe` blocking the master_bedroom doorway → triggers `score_doorway_accessibility` rule |
| `rooms_present` | `living`, `dining`, `kitchen`, `master_bedroom`, `study` |
| `wall_count` | 113 |

**Money-shot demo sequence (locked):** Design Agent proposes removing `wall_28` to enlarge the study → Compliance Agent emits a `structural_wall_protected` finding (severity `error`) → revise loop re-attempts → after N attempts hits `awaiting_human_approval` and is escalated to the coordinator. The backup target wall and the doorway-block fallback exist as safety nets if `wall_28` removal fails to be proposed.

---

## 2. Renovation Design Case — payload schema

### 2.1 Base shape decision

The Case payload **extends the `corpus/library/*.json` shape**, not the minimal `viewer/mcp-layout.json` shape.

Reasoning: the Design Agent needs top-level `rooms[]` for room-scoped MCP tools (`design_room`, `tag_room`, `compute_room_area`); the Compliance Agent needs `metadata.scale_m_per_px` and `image_shape_hw` for unit-correct findings. The viewer's minimal shape lacks both.

Base keys preserved unchanged: `version`, `metadata`, `rooms[]`, `items[]`. The existing layout normalizer at `src/haus/mcp_server.py` (`_normalize_item` ~line 105, `_normalize_layout` ~line 190) preserves unknown top-level keys, so the additions below are non-breaking.

### 2.2 Added top-level keys

| Key | Type | Required | Purpose |
|---|---|---|---|
| `case_id` | string (UUID v4) | yes | Stable identity; URL path segment. |
| `case_schema_version` | integer (1) | yes | Distinct from geometry `version`. Future-proofs schema evolution. |
| `created_at` | ISO-8601 UTC string | yes | Audit. |
| `updated_at` | ISO-8601 UTC string | yes | Bumped by every mutating endpoint. |
| `brief` | object (§2.7) | yes | Intake fields driving the Design Agent. |
| `design_status` | enum (§2.3) | yes | Lifecycle state. |
| `revise_count` | integer | yes | Auto-revise attempt counter; defaults to 0. |
| `compliance_findings` | array (§2.4) | yes | Most recent compliance run's findings. May be empty `[]`. |
| `approval_state` | object \| null (§2.5) | yes | Null until `awaiting_human_approval` is first reached. |
| `vendor_handoff` | object \| null (§2.6) | yes | Null until the handoff stage runs. |
| `pinned_proposal_id` | string \| null (§2.8) | yes | Reserved for demo replay; null in default Case. |
| `vendor_cache_key` | string \| null (§2.8) | yes | Reserved for vendor cache; null in default Case. |

### 2.3 Enum — `design_status`

Ordered, 9 values:

| Value | Semantics | Entered from | Entered via |
|---|---|---|---|
| `intake` | Case created, brief recorded, design not yet run. | (initial) | `POST /case` |
| `designing` | Design Agent is producing or has produced an `items[]` proposal. | `intake`, `revising` | `POST /case` (auto-advances), `POST /case/{id}/design` |
| `compliance_pending` | Design proposal exists; compliance has not run on it (or is about to). | `designing` | `POST /case/{id}/design` (terminal state of that call) |
| `revising` | Compliance returned errors and `revise_count < N`; Design Agent must re-plan. | `compliance_pending` | `POST /case/{id}/compliance` |
| `awaiting_human_approval` | Either compliance is clean OR `revise_count >= N`. Human reviewer (Stage 2: Action Center; Stage 1: PATCH stub) decides next. | `compliance_pending` | `POST /case/{id}/compliance` |
| `approved` | Human approved. Next: handoff. | `awaiting_human_approval` | (Stage 1) PATCH `approval_state.decision = "approved"`; (Stage 2) Action Center |
| `rejected` | Human rejected. Terminal-ish; Case may be re-opened by a new Case. | `awaiting_human_approval` | same as `approved` |
| `handoff_complete` | Vendor handoff package produced. | `approved` | (deferred — vendor stage not specified in this doc) |
| `closed` | Terminal. | `handoff_complete`, `rejected` | (deferred) |

`handoff_complete` and `closed` are present in the enum so Stage 2 has somewhere to go without re-amending this spec; their transitions are intentionally undefined here.

### 2.4 Shape — `compliance_findings[]` item

The load-bearing shape of the revise loop. The Design Agent's planner consumes `machine_hint` directly; it must not parse `reason`.

```json
{
  "rule_id": "structural_wall_protected",
  "severity": "error",
  "element_index": 28,
  "element_name": "wall_28",
  "coords": {"pos": [2.3226, 1.3, 0.4065], "geo": [2.3226, 2.6, 0.3]},
  "reason": "Cannot remove shelter wall (HDB structural).",
  "machine_hint": {
    "action": "do_not_remove",
    "constraint": "structural_wall",
    "hdb_type": "shelter",
    "alternative": "reshape using partition walls (hdb_type=partition) instead"
  }
}
```

Field rules:
- `rule_id` — stable string; must match one of the rules in §5.
- `severity` — `error` | `warn` | `info`. Only `error` triggers the revise loop / escalation.
- `element_name` — **canonical identity**. Matches `items[i].name` (present on every wall in `corpus/library/3.json` as `wall_0`, `wall_1`, …). Names are stable across revise rounds; indexes are not.
- `element_index` — hint only. May be stale after a revise round. Consumers locate the element by `element_name` first; `element_index` is for human readability / debug.
- `coords` — optional. Included when geometry is relevant to the finding.
- `reason` — human-readable. Renderable in Action Center or the demo overlay.
- `machine_hint` — required when `severity == "error"`. Free-form object with at minimum `action` and `constraint`; rule-specific additional keys allowed. The Design Agent's planner is fed the array of `machine_hint` objects directly in its prompt context.

### 2.5 Shape — `approval_state`

`null` until the Case first enters `awaiting_human_approval`. Once non-null, follows:

```json
{
  "decision": "pending",
  "reviewer": null,
  "decided_at": null,
  "notes": null,
  "escalation_reason": "Auto-revise exhausted (revise_count=3, N=3) on rule structural_wall_protected."
}
```

- `decision` — `pending` | `approved` | `rejected` | `sent_back`.
- `reviewer` — string identifier of the human (Stage 2: Action Center user; Stage 1: PATCH caller).
- `decided_at` — ISO-8601 UTC, set when `decision` transitions away from `pending`.
- `notes` — free-text from the reviewer.
- `escalation_reason` — populated only when the Case reaches `awaiting_human_approval` *via* the N-failure path (not the clean-design path). The text gives the reviewer immediate context.

### 2.6 Shape — `vendor_handoff`

```json
{
  "vendor_id": "vendor_007",
  "vendor_name": "Acme HDB Renovation Pte Ltd",
  "packet_uri": "file:///path/to/handoff/case_<id>/packet.zip",
  "cached": true
}
```

`cached: true` means the vendor was resolved from the local cache (`vendor_cache_key` matched), enabling offline demo recording. `cached: false` means a live search was used.

### 2.7 Shape — `brief`

Aligned with the existing `design_flat` MCP tool parameters (`src/haus/mcp_server.py` ~line 1159) so the HTTP service can pass the brief through unchanged.

```json
{
  "flat_type": "3-room BTO",
  "household_size": 2,
  "style_prompt": "minimalist Scandinavian, light wood, work-from-home corner",
  "constraints": ["no wall removal in shelter", "keep dining table for 4"],
  "must_keep_rooms": ["master_bedroom", "study"]
}
```

`constraints[]` and `must_keep_rooms[]` are advisory inputs to the LLM planner — they do **not** replace compliance rules. Compliance is the enforcement layer.

### 2.8 Determinism hooks

Both keys are reserved here; their subsystems are deferred to `TODO-9JUNE-START.md` §6 tasks F and E respectively. Implementations of the HTTP service must accept and persist these keys even before the subsystems exist.

- **`pinned_proposal_id`** — when non-null, `POST /case/{id}/design` MUST be deterministic for this Case: it returns a previously recorded `items[]` verbatim rather than calling an LLM. Subsystem (LLM replay cache, keyed by `(floor_plan_ref, brief) → items[]`) deferred.
- **`vendor_cache_key`** — when non-null, the eventual handoff stage MUST populate `vendor_handoff` from the local vendor cache rather than live search. Subsystem (cache lookup, fallback policy) deferred.

### 2.9 Canonical example payload

One worked example, exhibiting a Case mid-loop: design has run, compliance has flagged `wall_28` removal, the loop has not yet revised.

```json
{
  "version": 1,
  "case_schema_version": 1,
  "case_id": "c0a8012a-7e0c-4f51-9b3d-8b1b34d2f3e1",
  "created_at": "2026-06-09T10:14:22Z",
  "updated_at": "2026-06-09T10:17:48Z",
  "design_status": "compliance_pending",
  "revise_count": 0,
  "pinned_proposal_id": "demo-3room-orange-minimalist-v1",
  "vendor_cache_key": null,
  "brief": {
    "flat_type": "3-room BTO",
    "household_size": 2,
    "style_prompt": "minimalist Scandinavian, light wood, work-from-home corner",
    "constraints": ["no wall removal in shelter", "keep dining table for 4"],
    "must_keep_rooms": ["master_bedroom", "study"]
  },
  "metadata": {
    "name": "3-room orange BTO",
    "source": "tests/fixtures/bto_3room_orange.jpg",
    "image_shape_hw": [1086, 690],
    "scale_m_per_px": 0.009677,
    "wall_count": 113
  },
  "rooms": [
    {"id": "living", "label": "Living", "kind": "living",
     "bounds": {"x_min": -3.2, "z_min": 0.7, "x_max": 1.2, "z_max": 4.4}}
  ],
  "items": [
    {"type": "wall", "name": "wall_28", "pos": [2.3226, 1.3, 0.4065],
     "rot": 0, "visible": true, "geo": [2.3226, 2.6, 0.3],
     "color": 7874600, "hdb_type": "shelter"}
  ],
  "compliance_findings": [
    {
      "rule_id": "structural_wall_protected",
      "severity": "error",
      "element_index": 0,
      "element_name": "wall_28",
      "coords": {"pos": [2.3226, 1.3, 0.4065], "geo": [2.3226, 2.6, 0.3]},
      "reason": "Cannot remove shelter wall (HDB structural).",
      "machine_hint": {
        "action": "do_not_remove",
        "constraint": "structural_wall",
        "hdb_type": "shelter",
        "alternative": "reshape using partition walls (hdb_type=partition) instead"
      }
    }
  ],
  "approval_state": null,
  "vendor_handoff": null
}
```

The example is intentionally truncated to one room and one item — a real Case carries the full set from `corpus/library/3.json` (113 walls + furniture + 5 rooms).

---

## 3. Prerequisite gap — `hdb_type` propagation

> **CALLOUT — this prerequisite must land before the `structural_wall_protected` compliance rule can fire deterministically.**

**Statement.** Wall classification (`hdb_type ∈ {ferrolite, partition, structural, shelter}`) is set at `src/haus/extraction.py:396` (`_classify_wall_hdb`, via `_snap_to_hdb` at line 386) and persisted on `WallSegment.hdb_type` at `src/haus/types.py:32`. It propagates to pipeline metadata (`src/haus/pipeline.py`) but **does not reach per-item layout JSON**. Today the only signal on items is the color encoding (`5263440`=structural, `7874600`=shelter, `11842740`=partition, `9211040`=ferrolite). That signal is fragile: an agent can recolor a wall and bypass classification.

**Recommended fix (named, not designed here).** At layout serialization — the conversion point from `FloorPlanData` (which carries `WallSegment.hdb_type`) into the layout `items[]` list, in `src/haus/mesh.py` and/or `src/haus/pipeline.py` — emit an explicit `hdb_type` field on each wall item. The normalizer at `src/haus/mcp_server.py` (lines ~105–148) preserves unknown keys, so the addition is non-breaking. `src/haus/mesh.py` already knows the mapping in the other direction (`_COLOR_BY_HDB`); the symmetric serializer is small.

**Migration for existing library files.** `corpus/library/{1..4}.json` were generated before this fix. The Case ingest path (`POST /case`) must enrich on read by inverting `_COLOR_BY_HDB`: `color → hdb_type`. This buys correctness for the demo fixture without re-running vectorization.

**Safety / fail-open behaviour.** Walls created at runtime by `add_wall` (`src/haus/mcp_server.py` ~line 1256) currently get a generic color and will not have an explicit `hdb_type`. The `structural_wall_protected` rule fires **only when `hdb_type ∈ {structural, shelter}`**, so a missing classification fails *open* (the operation is allowed). This is the correct behaviour for the demo, which targets a *named existing* shelter wall.

---

## 4. HTTP endpoints

### 4.1 Endpoint table

| # | Method | Path | Purpose | `design_status` transition |
|---|---|---|---|---|
| 1 | POST | `/case` | Create Case from library JSON + brief | (none) → `intake` → `designing` |
| 2 | POST | `/case/{id}/design` | Run Design Agent | `designing` → `compliance_pending` |
| 3 | POST | `/case/{id}/compliance` | Run rules, emit findings | `compliance_pending` → `revising` OR `awaiting_human_approval` |
| 4 | POST | `/case/{id}/revise` | Replay findings into Design Agent | `revising` → `compliance_pending` OR `awaiting_human_approval` |
| 5 | GET  | `/case/{id}` | Read full Case | (no mutation) |

There is intentionally **no `/approve` endpoint** in Stage 1. Approval is a human action that lives in Action Center in Stage 2. Stage 1 satisfies the lifecycle via a PATCH-able `approval_state.decision` field (see §4.4 stub).

### 4.2 Per-endpoint detail

#### `POST /case`

| | |
|---|---|
| Request | `{floor_plan_ref: string, brief: <Brief object §2.7>, pinned_proposal_id?: string}` |
| `floor_plan_ref` | Path to a `corpus/library/*.json` file. **Library JSON only in Stage 1** — raster image paths are not accepted (additive in a later spec revision). |
| Response (201) | Full Case payload with newly minted `case_id`, `design_status: "designing"` (auto-advanced from `intake`), `revise_count: 0`, `compliance_findings: []`, `approval_state: null`, `vendor_handoff: null`. `hdb_type` enrichment runs during ingest. |
| Idempotency | Not idempotent. Each call mints a new `case_id`. Maestro will provide its own idempotency key in Stage 2 if needed. |
| Pre-state | n/a |
| Post-state | `designing` |
| Errors | `validation_failed` (bad brief shape, missing `floor_plan_ref`), `internal_error` (library file unreadable). |

#### `POST /case/{id}/design`

| | |
|---|---|
| Request | `{}` or `{style_override?: string}` |
| Response (200) | Full Case payload with updated `items[]`. `design_status: "compliance_pending"`. |
| Idempotency | **Idempotent when `pinned_proposal_id` is non-null** — the same proposal id returns identical `items[]`. This is the demo-replay hook. Without a pinned id, idempotency is best-effort. |
| Pre-state | `intake`, `revising` (when called by the revise loop). |
| Post-state | `compliance_pending` |
| Errors | `case_not_found`, `invalid_state_transition`. |

#### `POST /case/{id}/compliance`

| | |
|---|---|
| Request | `{}` |
| Response (200) | Full Case payload with populated `compliance_findings[]`. `design_status` per the rule below. |
| Post-state rule | Empty findings (no `error` severity) → `awaiting_human_approval` (clean design, go to human). Errors AND `revise_count < N` → `revising`. Errors AND `revise_count >= N` → `awaiting_human_approval` with `approval_state.escalation_reason` populated (lazy-initialised from null). |
| Idempotency | **Idempotent.** Pure read over current `items[]` + rules; same input → same findings. This is what makes findings safely replayable into `/revise`. |
| Pre-state | `compliance_pending` |
| Post-state | `revising` OR `awaiting_human_approval` |
| Errors | `case_not_found`, `invalid_state_transition`. |

#### `POST /case/{id}/revise`

| | |
|---|---|
| Request | `{findings: [<finding>, ...], increment_count?: boolean (default true)}` |
| Why findings in body | Caller can replay an older finding-set (useful for tests and the demo script); Stage 2 Maestro can pass the *same* findings object the Compliance Agent emitted without re-querying. |
| `increment_count` | `false` = replay without advancing the counter (demo aid). `true` = production behaviour. |
| Server behaviour | Pushes the array of `machine_hint` objects from `findings[]` into the Design Agent's planner context, re-runs the design. |
| Response (200) | Full Case payload with updated `items[]`. `design_status: "compliance_pending"` OR `awaiting_human_approval` if `increment_count: true` advanced `revise_count` to `>= N`. |
| Idempotency | Not idempotent when `increment_count: true` (counter advances). Idempotent when `increment_count: false`. |
| Pre-state | `revising` |
| Post-state | `compliance_pending` OR `awaiting_human_approval` |
| Errors | `case_not_found`, `invalid_state_transition`, `validation_failed` (malformed findings). |

#### `GET /case/{id}`

| | |
|---|---|
| Request | n/a |
| Response (200) | Full Case payload. |
| Idempotency | Trivially idempotent. |
| Errors | `case_not_found`. |

### 4.3 Universal contract rules

1. **Every mutating endpoint returns the full updated Case payload** — not a delta, not just an ack. This lets Stage 2 Maestro wire each stage as one "call → store full payload" step without a follow-up GET. It also saves the demo from a "now refresh the viewer" beat.
2. **Errors use a uniform envelope:** `{error: {code: string, message: string, hint?: string}}`. Defined codes: `case_not_found`, `invalid_state_transition`, `validation_failed`, `unauthorized`, `internal_error`. New codes require an amendment to this spec.
3. **Stage 1 persists Cases locally and mutates atomically per Case.** SQLite is the default local backend. There are still no ETags / If-Match / external optimistic-concurrency controls; callers should treat each mutating response as the new source of truth.
4. **`updated_at` is bumped by every mutating call** before the response is returned.
5. **Unknown fields in request bodies are ignored** (additive forward-compat). Unknown fields in the persisted Case payload are preserved across read/write cycles (matches existing normalizer behaviour at `src/haus/mcp_server.py:190`).

### 4.4 Revise-loop policy

**Default `N = 3`.** Configurable via `MAX_REVISE_ATTEMPTS` (HTTP service config / env var). Rationale: one attempt to learn from the finding, one to try an alternative, one as last-ditch. After three failed attempts the human reviewer is *more* useful than another machine retry — and three fits inside the 5-minute demo budget when the Design Agent uses pinned proposals.

**Demo override:** the demo video script should set `MAX_REVISE_ATTEMPTS=1` to force one revise → escalation in a single visible beat. Spec authorises this override.

**Stage-1 approval stub.** Since Action Center does not yet exist, the Stage-1 HTTP service exposes a PATCH-able transition `awaiting_human_approval` → `approved`/`rejected` directly on `approval_state.decision`. The PATCH endpoint shape is intentionally left for the implementer to define minimally (it does not appear in §4.1 because it is a temporary stub, not part of the orchestration boundary). **Stage 2 replaces this stub with Action Center wiring.**

---

## 5. Compliance rules in scope (v0)

Deliberately small. The rules below are the entire enforcement surface for Stage 1. Framing: *"extensible — additional rules plug into the same `compliance_findings[]` shape."*

### 5.1 `structural_wall_protected`

**Fires when:** a proposed mutation (`remove_object`, `move_object`, `resize_object`, or implicit equivalent via the Design Agent's `design_room`/`design_flat` outputs) targets any item where `type == "wall"` AND `hdb_type ∈ {structural, shelter}`.

**Severity:** `error`.

**Finding fields:** `element_name` set to the targeted wall's `name`. `coords` populated. `machine_hint`:
```json
{"action": "do_not_remove|do_not_move|do_not_resize", "constraint": "structural_wall", "hdb_type": "<structural|shelter>", "change_type": "remove|move|rotate|resize", "alternative": "reshape using partition walls (hdb_type=partition) instead"}
```

**Source of the money-shot demo failure** (see §1).

### 5.2 `doorway_accessibility`

**Fires when:** the score returned by `score_doorway_accessibility` (`src/haus/mcp_server.py` ~line 2314) for any room's doorway falls below a threshold (default `0.5`).

**Severity:** `error` if score `< 0.3`, `warn` otherwise.

**Finding fields:** `element_name` set to the blocking item's `name` (when identifiable). `machine_hint`:
```json
{"action": "do_not_block_doorway", "constraint": "min_clearance_m", "min_clearance_m": 0.9, "doorway_room": "<room_id>"}
```

**Backup demo failure mode** (see §1 `fallback_failure_mode`).

### 5.3 Findings replay contract

The output of `POST /case/{id}/compliance` (specifically the `compliance_findings` array) **must be valid as the `findings` request-body field of `POST /case/{id}/revise`**, unchanged. This guarantees:

- The same findings can be replayed deterministically (tests, demo, debugging).
- Stage 2 Maestro can forward findings between stages without transformation.
- New rules added later must respect the same shape (§2.4) or the contract breaks.

---

## 6. Determinism for the demo

The two reserved keys in §2.8 are the contract surface.

- **`pinned_proposal_id`** — when set on a Case, `POST /case/{id}/design` MUST return a previously recorded `items[]` verbatim rather than calling an LLM. The recording mechanism (keying, storage, invalidation) is the subject of `TODO-9JUNE-START.md` §6 task F. This spec only reserves the key and the determinism contract: *"if non-null, `/design` MUST be deterministic for this Case."*
- **`vendor_cache_key`** — when set, the handoff stage reads the local vendor cache first. On cache miss, TinyFish live search may populate the cache when `TINYFISH_API_KEY` is set; otherwise the deterministic stub fallback is used.

Implementations of the HTTP service must accept, persist, and round-trip both keys.

---

## 7. What this spec does NOT cover

Out of scope, explicitly:

- **Code.** No Python, no JSON Schema definitions in JSON Schema format, no OpenAPI document. Those are implementation outputs.
- **Maestro Case mapping.** Which stages exist, how transitions fire, retry policies at the Maestro layer — all Stage 2. A future `SPEC-MAESTRO-WIRING.md` will reference this doc.
- **Action Center wire format.** The schema of the approval task, the renderer for findings/before-after, the routing rules — all Stage 2.
- **Full vendor agent.** TinyFish live search exists; richer ranking, contact extraction, Serper, and contract generation are deferred.
- **Auth beyond a local Bearer token, multi-tenancy, rate-limiting.** Stage 1 is still a single-tenant local service.
- **Persistence beyond local SQLite.** External DBs, cloud persistence, and distributed locking are deferred.
- **Additional compliance rules** beyond the two in §5.
- **Migration story** for older `corpus/library/*.json` files — handled inline by the ingest enrichment in §3.

---

## 8. Acceptance criteria for this spec

The spec is **done** when all six check:

1. [ ] An unfamiliar reader can, from this document alone, hand-construct a valid Case payload that round-trips through `POST /case` → `POST /case/{id}/design` → `POST /case/{id}/compliance` → `POST /case/{id}/revise` without ambiguity.
2. [ ] The `design_status` enum (§2.3), the `compliance_findings[]` shape (§2.4), and the endpoint state-transition table (§4.1 + §4.2 post-states) together uniquely determine the post-state of every mutating call.
3. [ ] The `hdb_type` gap is called out as a prerequisite (§3), references `src/haus/extraction.py:386, 396` and `src/haus/types.py:32`, names `src/haus/mesh.py` / `src/haus/pipeline.py` as the fix location, and prescribes no implementation.
4. [ ] The demo fixture pin (§1) appears verbatim — image, layout, target walls, fallback failure — and is referenced as the single source of truth.
5. [ ] §7 explicitly excludes code, Maestro mapping, Action Center, full vendor automation, external identity/storage, and additional rules.
6. [ ] `pinned_proposal_id` and `vendor_cache_key` are reserved keys (§2.8, §6) with one-paragraph contracts, subsystems undesigned.

---

## Appendix A — Worked round-trip (verification aid)

Using only this spec, this is the expected lifecycle of the demo Case with `MAX_REVISE_ATTEMPTS=3`:

| Step | Call | `design_status` after | `revise_count` after | `compliance_findings` after | `approval_state` after |
|---|---|---|---|---|---|
| 1 | `POST /case` | `designing` | 0 | `[]` | `null` |
| 2 | `POST /case/{id}/design` | `compliance_pending` | 0 | `[]` | `null` |
| 3 | `POST /case/{id}/compliance` (errors found) | `revising` | 0 | `[wall_28 finding]` | `null` |
| 4 | `POST /case/{id}/revise` (`increment_count: true`) | `compliance_pending` | 1 | `[wall_28 finding]` (carried forward) | `null` |
| 5 | `POST /case/{id}/compliance` (still errors) | `revising` | 1 | `[wall_28 finding]` | `null` |
| 6 | `POST /case/{id}/revise` | `compliance_pending` | 2 | `[…]` | `null` |
| 7 | `POST /case/{id}/compliance` (still errors) | `revising` | 2 | `[wall_28 finding]` | `null` |
| 8 | `POST /case/{id}/revise` | `compliance_pending` | 3 | `[…]` | `null` |
| 9 | `POST /case/{id}/compliance` (errors AND `revise_count >= N`) | `awaiting_human_approval` | 3 | `[wall_28 finding]` | `{decision: "pending", escalation_reason: "Auto-revise exhausted (revise_count=3, N=3) on rule structural_wall_protected."}` |
| 10 | (Stage-1 stub) PATCH `approval_state.decision = "approved"` | `approved` | 3 | (unchanged) | `{decision: "approved", reviewer: "<id>", decided_at: "…"}` |

If a future reader can reproduce this table from §2–§5 without re-reading the table itself, acceptance criterion 1 holds.
