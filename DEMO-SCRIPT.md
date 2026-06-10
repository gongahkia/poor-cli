# DEMO-SCRIPT - UiPath AgentHack video and screenshots

> Target: 5 minutes max. Show software running. Do not spend the video on slides.

## 1. Generate the final demo Case

```console
$ .venv/bin/haus case demo --fixture corpus/library/3.json --pinned demo_3room_remove_wall_28 --max-revise-attempts 1 --out asset/demo/case-demo.json
```

Expected terminal beats:

```text
create: status=designing
design: status=compliance_pending
compliance#1: status=revising
revise#1: status=compliance_pending
compliance#2: status=awaiting_human_approval
approval: status=approved
handoff: status=handoff_complete
case_json=asset/demo/case-demo.json
viewer_command=haus view --case asset/demo/case-demo.json
```

Open the visual review:

```console
$ .venv/bin/haus view --case asset/demo/case-demo.json --port 8080
```

Run the HTTP smoke path against a live server:

```console
$ HAUS_CASE_API_TOKEN=dev-token .venv/bin/haus case-server --port 8090 --api-token dev-token --proposals-dir tests/fixtures/proposals --vendor-cache-dir tests/fixtures/vendors
$ HAUS_CASE_API_TOKEN=dev-token .venv/bin/python scripts/case_smoke.py --base-url http://127.0.0.1:8090 --max-revise-attempts 1
```

## 2. Stage-1 fallback if UiPath access is still pending

Use this only if Automation Cloud/Labs access is unavailable at recording time.

1. Show the local HTTP lifecycle in terminal using `scripts/case_smoke.py`.
2. Show `asset/demo/case-demo.json` in the Three.js Case Review viewer.
3. Show `SPEC-MAESTRO-WIRING.md` for the exact Maestro stage mapping.
4. Show `SPEC-ACTION-CENTER.md` for the coordinator task copy and payload.
5. State plainly: `UiPath Action Center/Maestro wiring is pending tenant access; the local service is the already-working orchestration boundary.`

Do not fake an Action Center screenshot.

## 3. Five-minute script

### 0:00-0:25 Problem

`Renovation teams can now ask AI for layout ideas, but the risky part is governance: structural-wall mistakes, repeated revisions, and contractor handoff. Haus turns an HDB floor plan into editable 3D geometry, then UiPath governs the design-to-approval workflow.`

Visual: title slide or README, then immediate switch to viewer.

### 0:25-0:55 Architecture

`Maestro Case is the Case Manager. It routes Intake, Design, Compliance, Human Approval, and Contractor Handoff. Haus is the external geometry and compliance service. Action Center is where the renovation coordinator makes the approval decision.`

Visual: [`asset/reference/architecture.png`](./asset/reference/architecture.png) or the README architecture section.

### 0:55-2:35 Money shot

`The Design Agent proposes a renovation concept for a pinned 3-room BTO fixture. The proposal removes wall_28 to enlarge the study. Haus knows wall_28 is a shelter wall, so the Compliance Agent blocks it with a structured finding. Maestro sends that finding back through the revise loop. After the configured retry threshold, the Case is escalated instead of silently continuing.`

Visuals:

- terminal running `haus case demo`
- Three.js Case Review with before/current diff
- highlighted `structural_wall_protected` finding
- `approval_state.escalation_reason`

### 2:35-3:35 Human in the loop

`The coordinator sees the same Case in Action Center: the before/after link, the blocked wall, the machine-readable finding, and the vendor handoff preview. The coordinator can approve, reject, or send back. That decision is written back to the Case before handoff.`

Visual:

- real Action Center task if access exists
- otherwise show `SPEC-ACTION-CENTER.md` and state it is pending access

### 3:35-4:20 Contractor handoff

`After approval, the Vendor/Handoff Agent creates a packet for a cached HDB renovation contractor. The recorded demo is cache-first for reliability, but the same agent can use TinyFish search when configured.`

Visuals:

- `handoff: status=handoff_complete`
- `vendor_handoff.vendor_name`
- packet URI / ZIP contents (`handoff.json`, `summary.md`)

### 4:20-4:45 Coding-agent bonus

`Codex was used as the coding agent for the Haus-side build. After UiPath CLI auth lands, the intended capture is uip skills install --agent codex followed by the pack/publish/deploy chain for the UiPath project.`

Visual:

- `uip skills install --agent codex` only after installed/authed
- if not available, show README pending-access note

### 4:45-5:00 Impact

`The point is not another layout generator. The point is a governed renovation workflow: agents can propose and retry, geometry checks can block, humans stay in charge, and the contractor receives an auditable handoff package.`

## 4. Screenshot checklist

Required:

- Devpost cover: Three.js Case Review showing floor plan + highlighted finding.
- Before/after Case Review: baseline ghost and proposed design.
- Terminal lifecycle: `create -> design -> compliance -> revise -> awaiting_human_approval -> approval -> handoff`.
- Compliance finding details: `structural_wall_protected`, `wall_28`, severity `error`.
- Action Center coordinator task with approve/reject/send-back controls. Pending until access.
- Vendor handoff packet evidence: `vendor_handoff.vendor_name` and packet ZIP contents.
- README UiPath components section.
- Public repo license visible.

Optional:

- UiPath Maestro process/stage diagram.
- `uip skills install --agent codex` and pack/publish/deploy flow.
- TinyFish fallback/cache behavior.

## 5. Recording notes

- Use `--max-revise-attempts 1` for video timing.
- Use pinned proposal `demo_3room_remove_wall_28` for deterministic failure.
- Keep `TINYFISH_API_KEY` optional; the cache-first vendor path is enough.
- Keep `HAUS_CASE_API_TOKEN` enabled for HTTP/tunnel demos.
- Do not show real secrets, tunnel tokens, or private UiPath tenant ids.

## Sources

- UiPath AgentHack Devpost deliverables: <https://uipath-agenthack.devpost.com/>
- UiPath AgentHack rules: <https://uipath-agenthack.devpost.com/rules>
