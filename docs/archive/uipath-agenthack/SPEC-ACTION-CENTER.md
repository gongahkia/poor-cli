# SPEC-ACTION-CENTER - Renovation coordinator approval

> Status: Implementation-ready before UiPath access. Exact tenant folder, Action App id, catalog id, and assignee names are pending Automation Cloud/Labs access.

## 1. Reviewer

**Persona:** internal renovation coordinator/designer.

**Job:** decide whether a Haus-generated renovation design can move to contractor handoff after automated compliance checks. The coordinator is the human source of record. The Three.js Case Review view is only the visual evidence surface.

**UiPath surface:** Action Center App task rendered by a UiPath Action App. This matches the current Action Center model where an App task uses Apps for the visual interface and action properties for input fields. Source: <https://docs.uipath.com/action-center/automation-cloud/latest/user-guide/create-user-action>.

## 2. Task copy

### Escalated blocked design

**Title**

`Haus review: protected-wall exception for Case {{case_id_short}}`

**Description**

`Haus generated a renovation layout, but the Compliance Agent found an unresolved protected-wall violation after {{revise_count}} revise attempt(s). Review the before/after render, compliance finding, and contractor handoff preview. Approve only if the coordinator accepts the exception for demo handoff; otherwise reject or send the case back with required changes.`

**Primary instruction**

`Check whether the proposed design is acceptable for internal coordinator approval before contractor handoff. Compliance findings are machine-generated and should be treated as blocking unless the coordinator records an override reason.`

### Clean design

**Title**

`Haus review: clean design for Case {{case_id_short}}`

**Description**

`Haus generated a renovation layout with no blocking compliance errors. Review the layout, brief, and handoff preview before approving contractor handoff.`

**Primary instruction**

`Approve if the design matches the brief and the coordinator is ready to send the handoff packet to a contractor. Send back for design changes. Reject if the case should not continue.`

## 3. Escalation reasons

Use these machine values in Maestro and render the human text beside them.

| Code | Human text | Trigger |
|---|---|---|
| `auto_revise_exhausted` | `Auto-revise exhausted; blocking compliance findings remain.` | `design_status == awaiting_human_approval`, `approval_state.escalation_reason != null` |
| `clean_design_gate` | `Clean design requires coordinator sign-off before handoff.` | no `error` findings |
| `manual_quality_gate` | `Manual quality gate requested by Case Manager.` | demo/operator override |
| `vendor_selection_required` | `Coordinator must pick a contractor for handoff.` | multiple vendor options |

## 4. Action input payload

Pass this object from Maestro to the Action App. Names are stable; UiPath-specific variable casing can be adjusted after tenant access.

```json
{
  "case_id": "uuid",
  "case_id_short": "first-8-chars",
  "case_api_url": "https://<tunnel-or-host>/case/<case_id>",
  "viewer_url": "https://<viewer-host>/viewer/editor.html?case=<case-json-url>",
  "design_status": "awaiting_human_approval",
  "revise_count": 1,
  "max_revise_attempts": 1,
  "escalation_code": "auto_revise_exhausted",
  "escalation_reason": "Auto-revise exhausted (revise_count=1, N=1) on rule structural_wall_protected.",
  "brief": {
    "flat_type": "3-room BTO",
    "household_size": 2,
    "style_prompt": "minimalist renovation concept",
    "constraints": ["preserve HDB structural and shelter walls"],
    "must_keep_rooms": []
  },
  "finding_summary": {
    "total": 1,
    "errors": 1,
    "rules": ["structural_wall_protected"],
    "elements": ["wall_28"]
  },
  "compliance_findings": [
    {
      "rule_id": "structural_wall_protected",
      "severity": "error",
      "element_name": "wall_28",
      "reason": "Cannot remove shelter wall (HDB structural).",
      "machine_hint": {
        "action": "do_not_remove",
        "constraint": "structural_wall",
        "hdb_type": "shelter",
        "change_type": "remove"
      }
    }
  ],
  "diff_summary": {
    "removed_walls": ["wall_28"],
    "moved_walls": [],
    "resized_walls": [],
    "added_items": 0,
    "removed_items": 1
  },
  "vendor_options": [
    {
      "vendor_id": "vendor_haus_001",
      "vendor_name": "Keystone HDB Renovation Pte Ltd",
      "service_area": "Singapore",
      "specialties": ["HDB renovation", "BTO space planning", "compliance handoff"]
    }
  ],
  "handoff_preview": {
    "packet_will_include": ["handoff.json", "summary.md"],
    "vendor_cache_key": "demo_hdb_renovation",
    "cached": true
  }
}
```

## 5. Action fields

### Read-only fields

| Field | Type | Render |
|---|---|---|
| `case_id` | text | monospace |
| `viewer_url` | link | open Case Review |
| `design_status` | text | status pill |
| `revise_count` | number | `{{revise_count}} / {{max_revise_attempts}}` |
| `escalation_reason` | text | warning panel if non-null |
| `brief` | object | compact key/value section |
| `compliance_findings` | array | table: severity, rule, element, reason |
| `diff_summary` | object | removed/moved/resized walls |
| `vendor_options` | array | radio/select list |

### Reviewer input fields

| Field | Type | Required | Rule |
|---|---|---|---|
| `decision` | enum | yes | `approved`, `rejected`, `sent_back` |
| `reviewer_notes` | multiline text | yes for `rejected`/`sent_back`; optional for `approved` | stored in `approval_state.notes` |
| `override_reason` | multiline text | yes if `approved` and any `error` findings remain | include in notes |
| `selected_vendor_id` | string | yes for `approved` | passed to `/handoff` |
| `requested_changes` | multiline text | yes for `sent_back` | appended to notes |

### Buttons / task actions

Action Center `Complete Task` expects `Task Action` to match the form button property name and `TaskData` to contain form values. Source: <https://docs.uipath.com/action-center/automation-cloud/latest/user-guide/complete-task>.

| Button label | Property name / Task Action | Output `decision` |
|---|---|---|
| Approve handoff | `approve` | `approved` |
| Reject case | `reject` | `rejected` |
| Send back | `send_back` | `sent_back` |

## 6. Decision mapping

After the Action task completes, Maestro maps `TaskData` to the Stage-1 HTTP stub:

```http
PATCH /case/{case_id}/approval
Authorization: Bearer {{HAUS_CASE_API_TOKEN}}
Content-Type: application/json
```

```json
{
  "decision": "approved",
  "reviewer": "{{ActionCompletedBy}}",
  "notes": "{{reviewer_notes}}\nOverride: {{override_reason}}"
}
```

Then:

| Decision | Next Maestro step | Haus call |
|---|---|---|
| `approved` | Contractor handoff | `POST /case/{case_id}/handoff` with `vendor_cache_key`, optional `vendor_id` |
| `rejected` | Closed/rejected | no handoff |
| `sent_back` | Design revision branch | Stage 2 should record the decision, then route back to Design/Revise with coordinator notes. Current Stage-1 PATCH keeps `design_status == awaiting_human_approval`. |

## 7. Routing

| Setting | Value |
|---|---|
| Task catalog | `HausRenovationReview` |
| Priority | `High` for compliance errors; `Medium` for clean-design gate |
| Assignee group | `Renovation Coordinators` |
| SLA target | 1 business day for production; immediate for demo |
| Attachments | optional screenshot bundle; do not attach the full ZIP handoff packet before approval |

## 8. Demo narration

`The agents do not silently ship a risky layout. Maestro routes the case to Action Center, where an internal renovation coordinator sees the exact wall, the compliance reason, the before/after review link, and the vendor handoff preview. The coordinator decision is written back to the Case before any contractor package is generated.`

## 9. Pending access checks

- Create the Action App and confirm exact action property names.
- Confirm whether the deployed Action App returns `TaskData` directly to Maestro or through a workflow activity in the tenant.
- Confirm folder/catalog/assignee ids.
- Replace Stage-1 PATCH stub with the real Action Center completion branch once UiPath access exists.

## Sources

- UiPath Action Center Create App Task: <https://docs.uipath.com/action-center/automation-cloud/latest/user-guide/create-user-action>
- UiPath Action Center Complete Task: <https://docs.uipath.com/action-center/automation-cloud/latest/user-guide/complete-task>
- UiPath Maestro task types: <https://docs.uipath.com/maestro/automation-cloud/latest/user-guide/tasks>
