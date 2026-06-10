# SUBMISSION-DRAFT - UiPath AgentHack

## 1. Devpost copy

### Title

`Haus: governed AI renovation design for HDB flats`

### Tagline

`Maestro-orchestrated design, compliance, human approval, and contractor handoff for AI-generated renovation layouts.`

### Track

`Track 1 - UiPath Maestro Case`

### Short description

Haus turns Singapore HDB/BTO floor plans into editable 3D layouts, then runs a governed multi-agent renovation workflow: intake, design generation, compliance checks, human coordinator approval, and contractor handoff. The key demo path is a risky design proposal that removes a protected shelter wall. The Compliance Agent blocks it, the revise loop retries, and Maestro escalates to Action Center when automation should stop and a human should decide.

### Business problem

Interior design and renovation teams can use AI to generate layouts quickly, but the operational risk sits after generation: compliance mistakes, repeated redesign loops, untracked human overrides, and weak contractor handoff. A renovation firm needs a governed workflow where agents can work fast, deterministic spatial rules can block unsafe changes, and a coordinator remains accountable before any handoff leaves the firm.

### How it works

1. Intake creates a Renovation Design Case from a real HDB/BTO floor-plan layout and customer brief.
2. The Design Agent proposes layout changes against Haus geometry.
3. The Compliance Agent checks protected walls and accessibility/walkway constraints.
4. If findings are blocking, the Case Manager routes them back through a revise loop.
5. After the retry threshold, Maestro escalates to Action Center for an internal renovation coordinator.
6. If approved, the Vendor/Handoff Agent creates a contractor packet with the approved Case, findings, and summary.

### UiPath components

- UiPath Maestro Case: stage orchestration and retry/escalation governance.
- UiPath Action Center + Apps: human coordinator approval.
- UiPath API Workflow or external workflow task: calls into the Haus HTTP Case service.
- Agent Builder: planned thin low-code Intake/brief agent after access.
- UiPath CLI + UiPath for Coding Agents: planned Codex-assisted pack/publish/deploy capture for bonus points.

### Agent type statement

Haus uses a combination:

- Coding agent: OpenAI Codex for code/spec/test work and planned UiPath CLI workflow after `uip` access.
- External coded agents: Haus Design Agent, Compliance Agent, Revise Loop, Vendor/Handoff Agent in Python.
- Low-code/native UiPath agents: planned Agent Builder/Action Center/Maestro components once tenant access lands.

### Technical execution

The Haus-side service is already runnable without UiPath:

- Starlette/Uvicorn HTTP API.
- SQLite persistence by default.
- optional Bearer auth with `HAUS_CASE_API_TOKEN`.
- deterministic pinned proposals for recorded demos.
- cache-first vendor handoff with TinyFish live search when configured.
- compliance findings with machine-readable hints for the revise loop.
- Three.js Case Review viewer for before/after evidence.

### Impact

The prototype turns AI design from a one-shot suggestion tool into a governed case workflow. It is applicable to renovation firms, property managers, and compliance-heavy design teams where generated outputs need validation, human accountability, and auditable downstream handoff.

### Current status

Stage 1 local flow is implemented and test-covered. Stage 2 UiPath wiring is pending Labs/Automation Cloud access: Maestro Case stages, Action Center task deployment, and UiPath CLI pack/publish/deploy capture.

## 2. Architecture section

```text
UiPath Maestro Case
  - Case Manager: owns lifecycle, retry threshold, escalation
  - Intake stage: creates Renovation Design Case
  - Design stage: calls Haus Design Agent
  - Compliance stage: calls Haus Compliance Agent
  - Revise stage: replays structured findings
  - Human Approval: Action Center coordinator task
  - Contractor Handoff: calls Haus Vendor/Handoff Agent

Haus HTTP Case Service
  - POST /case
  - POST /case/{id}/design
  - POST /case/{id}/compliance
  - POST /case/{id}/revise
  - PATCH /case/{id}/approval
  - POST /case/{id}/handoff
  - GET /case/{id}

Haus viewer
  - Three.js before/after Case Review
  - compliance finding highlights
  - vendor/approval state display
```

## 3. README checklist

- [x] Project description.
- [x] Setup instructions.
- [x] MIT license.
- [x] Stage-1 local fallback demo.
- [x] UiPath components planned/used.
- [x] Coding-agent vs low-code/native agent split.
- [x] HTTP auth example with `HAUS_CASE_API_TOKEN`.
- [x] Public demo Case artifact.
- [ ] Real Maestro screenshots after access.
- [ ] Real Action Center screenshot after access.
- [ ] `uip` CLI pack/publish/deploy capture after auth.
- [ ] Deck link.
- [ ] Devpost video link.

## 4. Public repo checklist

- [x] Root `README.md`.
- [x] Detectable `LICENSE`.
- [x] Specs: HTTP, Maestro, Action Center.
- [x] Demo script.
- [x] Smoke script.
- [x] Demo fixture and pinned proposal.
- [x] Vendor cache fixture.
- [x] No secrets committed.
- [ ] Confirm repo visibility public.
- [ ] Confirm GitHub About license detection.
- [ ] Add final Devpost/video links when available.

## 5. Deck outline

1. Problem: AI renovation ideas need governance.
2. Solution: Haus + UiPath Maestro Case.
3. Architecture: Maestro, Action Center, Haus HTTP service, Three.js viewer.
4. Demo flow: protected-wall failure and revise loop.
5. Human-in-loop: Action Center coordinator decision.
6. Handoff: contractor packet.
7. Technical depth: compliance findings, SQLite/auth, deterministic replay, vendor cache/TinyFish fallback.
8. Impact/adoption.
9. Roadmap: broader HDB rules, production identity, hosted service, richer vendor ranking.

## 6. Product feedback prompts

- Maestro Case is a strong conceptual fit for exception-heavy workflows, but first-time builders need a minimal external-HTTP example that shows variable handoff between stages.
- Action Center/App task docs should include a compact approval-task template with button actions and JSON output mapping.
- UiPath for Coding Agents should expose an end-to-end AgentHack starter path: install CLI, auth, install Codex skills, pack, publish, deploy, verify.
- Local-to-cloud development would benefit from official tunnel/auth guidance for hackathon prototypes.

## Sources

- Devpost deliverables and README requirements: <https://uipath-agenthack.devpost.com/>
- Devpost rules and judging criteria: <https://uipath-agenthack.devpost.com/rules>
- UiPath AgentHack resources: <https://uipath-agenthack.devpost.com/resources>
- UiPath CLI with Coding Agents: <https://docs.uipath.com/uipath-cli/standalone/latest/user-guide/coding-agents>
