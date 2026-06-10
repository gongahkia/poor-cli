# SPEC-MAESTRO-WIRING - Stage 2 UiPath orchestration

> Status: Implementation-ready before UiPath access. Exact Maestro designer labels and tenant ids are pending Automation Cloud/Labs access.

## 1. Goal

Wrap the existing Haus Stage-1 HTTP service with UiPath Maestro Case so UiPath owns orchestration, retry decisions, human approval, and handoff governance. Haus remains the deterministic geometry/compliance service.

Primary Stage-1 contract: [`SPEC-HTTP-CASE.md`](./SPEC-HTTP-CASE.md).

## 2. UiPath components

| Component | Role |
|---|---|
| Maestro Case | Case Manager, stage transitions, branching, retry governance |
| Action Center + Apps | internal coordinator approval task |
| API Workflows or external workflow task | HTTP calls into Haus Case service |
| Agent Builder | optional thin Intake/brief agent after access |
| UiPath CLI + Codex skills | coding-agent bonus capture; pack/publish/deploy once project exists |

Current Maestro docs list task types for Action App tasks, external agents/workflows over APIs, API workflows, and agentic processes. Source: <https://docs.uipath.com/maestro/automation-cloud/latest/user-guide/tasks>.

## 3. Process variables

| Variable | Type | Owner | Notes |
|---|---|---|---|
| `caseJson` | object/string JSON | Maestro | full latest Case payload; canonical state |
| `caseId` | string | Maestro | copied from `caseJson.case_id` |
| `hausBaseUrl` | string | config | public tunnel or hosted URL |
| `hausApiToken` | secret | UiPath asset/credential | sent as Bearer token |
| `maxReviseAttempts` | number | config | usually 1 for video, 3 for normal run |
| `findings` | array | Compliance stage | copied from `caseJson.compliance_findings` |
| `actionTaskId` | integer/string | Action Center | pending exact return type |
| `selectedVendorId` | string/null | coordinator | optional `/handoff` selector |
| `vendorCacheKey` | string | config | `demo_hdb_renovation` for recorded demo |

Rule: after every mutating Haus call, replace `caseJson` with the full response body before branching.

## 4. Stage map

```text
INTAKE -> DESIGN -> COMPLIANCE
                     | status=revising
                     v
                   REVISE -> COMPLIANCE
                     |
                     | status=awaiting_human_approval
                     v
HUMAN_APPROVAL -> CONTRACTOR_HANDOFF -> CLOSED
        |
        | rejected
        v
      CLOSED_REJECTED
```

## 5. Endpoint calls

All calls include:

```http
Authorization: Bearer {{hausApiToken}}
Content-Type: application/json
```

### 5.1 Intake

**Task:** API workflow or external workflow.

```http
POST {{hausBaseUrl}}/case
```

```json
{
  "floor_plan_ref": "corpus/library/3.json",
  "brief": {
    "flat_type": "3-room BTO",
    "household_size": 2,
    "style_prompt": "minimalist renovation concept",
    "constraints": ["preserve HDB structural and shelter walls"],
    "must_keep_rooms": []
  },
  "pinned_proposal_id": "demo_3room_remove_wall_28",
  "vendor_cache_key": "demo_hdb_renovation"
}
```

**Store:** `caseJson = response`, `caseId = response.case_id`.

### 5.2 Design

```http
POST {{hausBaseUrl}}/case/{{caseId}}/design
```

```json
{}
```

**Expected status:** `compliance_pending`.

### 5.3 Compliance

```http
POST {{hausBaseUrl}}/case/{{caseId}}/compliance
```

```json
{}
```

**Branch:**

| `caseJson.design_status` | Next |
|---|---|
| `revising` | Revise |
| `awaiting_human_approval` | Human Approval |
| other | Incident/manual stop |

### 5.4 Revise

```http
POST {{hausBaseUrl}}/case/{{caseId}}/revise
```

```json
{
  "findings": "{{caseJson.compliance_findings}}",
  "increment_count": true
}
```

**Branch:** back to Compliance unless response already returns `awaiting_human_approval`.

### 5.5 Human Approval

**Task:** Create Action App task in Action Center.

Input payload: see [`SPEC-ACTION-CENTER.md`](./SPEC-ACTION-CENTER.md#4-action-input-payload).

Output fields:

```json
{
  "decision": "approved",
  "reviewer_notes": "Approved for contractor handoff demo.",
  "override_reason": "Demo coordinator accepts blocked proposal for governed handoff proof.",
  "selected_vendor_id": "vendor_haus_001",
  "requested_changes": ""
}
```

Then write the decision to Haus:

```http
PATCH {{hausBaseUrl}}/case/{{caseId}}/approval
```

```json
{
  "decision": "{{decision}}",
  "reviewer": "{{ActionCompletedBy}}",
  "notes": "{{reviewer_notes}}"
}
```

**Branch:**

| Decision | Next |
|---|---|
| `approved` | Contractor Handoff |
| `rejected` | Closed Rejected |
| `sent_back` | Design/Revise branch with coordinator notes |

### 5.6 Contractor Handoff

```http
POST {{hausBaseUrl}}/case/{{caseId}}/handoff
```

```json
{
  "vendor_cache_key": "demo_hdb_renovation",
  "vendor_id": "{{selectedVendorId}}"
}
```

**Expected status:** `handoff_complete`. Store `caseJson.vendor_handoff.packet_uri` for demo evidence.

### 5.7 Read/refresh

```http
GET {{hausBaseUrl}}/case/{{caseId}}
```

Use after incidents, unclear task retries, or viewer refresh.

## 6. Retry and incident policy

Do not apply blind retries to every mutating endpoint. The Stage-1 service persists with local SQLite and mutates atomically per Case, but not every call is idempotent.

| Call | Retry policy |
|---|---|
| `POST /case` | no automatic retry after request was sent; if timeout occurs before `caseId` is known, create a new case only after operator confirmation |
| `POST /design` | retry once on 5xx/timeout when `pinned_proposal_id` is set; otherwise refresh with `GET` first |
| `POST /compliance` | safe to retry on 5xx/timeout; compliance is deterministic over current `items[]` |
| `POST /revise` | no blind retry because `increment_count=true` changes state; on timeout, `GET /case/{id}` and branch from saved status |
| `PATCH /approval` | on timeout, `GET`; retry only if status remains `awaiting_human_approval` and decision not recorded |
| `POST /handoff` | on timeout, `GET`; retry only if status remains `approved` |

Transport handling:

- Retry at most 2 times for `429`, `502`, `503`, `504`, and network timeouts where the row above allows it.
- Backoff: 2s, then 5s. Use jitter if available.
- Do not retry `400`, `401`, `404`, or `409`; route to incident/manual review.
- Persist request/response bodies in the Maestro run log where policy allows. Do not log `hausApiToken`.

## 7. Concurrency

- One Maestro Case instance owns one Haus Case id.
- Never run two mutating Haus calls for the same `caseId` in parallel.
- Treat the latest mutating response as the new source of truth.
- If two users touch the same Action task, use Action Center completion as the single decision source and refresh `caseJson` before handoff.

## 8. Local endpoint exposure

Local dev command:

```console
$ HAUS_CASE_API_TOKEN=dev-token .venv/bin/haus case-server --port 8090 --case-db-path ~/.haus/cases/cases.sqlite3 --proposals-dir tests/fixtures/proposals --vendor-cache-dir tests/fixtures/vendors
```

Tunnel examples for the Maestro spike:

```console
$ cloudflared tunnel --url http://127.0.0.1:8090
$ ngrok http 8090
```

Set `hausBaseUrl` to the HTTPS tunnel URL and keep `HAUS_CASE_API_TOKEN` enabled. Do not commit tunnel URLs or tokens.

## 9. Spike A acceptance

Smallest proof after UiPath access lands:

1. Start the local Haus server with Bearer auth.
2. Expose it with a tunnel.
3. In Maestro, create a two-stage process: Intake calls `POST /case`, Design calls `POST /case/{id}/design`.
4. Store the full response payload from each call in `caseJson`.
5. Confirm the Design stage can read `caseJson.case_id` from the Intake output.
6. Confirm a failed auth token returns `401` and routes to incident/manual stop.

Passing this proves HTTP packaging is enough. Failing it decides whether to use a UiPath API Workflow wrapper, queue/Robot bridge, or a hosted service.

## 10. Pending access checks

- Confirm exact Maestro task labels for external workflow/API workflow calls.
- Confirm JSON object variable support versus string serialization in the current tenant.
- Confirm Action App task output shape.
- Confirm CLI commands for pack/publish/deploy of the final Maestro/Action App solution.

## Sources

- UiPath AgentHack Devpost requirements: <https://uipath-agenthack.devpost.com/>
- UiPath AgentHack rules: <https://uipath-agenthack.devpost.com/rules>
- UiPath Maestro task types: <https://docs.uipath.com/maestro/automation-cloud/latest/user-guide/tasks>
- UiPath CLI with Codex skills: <https://docs.uipath.com/uipath-cli/standalone/latest/user-guide/coding-agents>
