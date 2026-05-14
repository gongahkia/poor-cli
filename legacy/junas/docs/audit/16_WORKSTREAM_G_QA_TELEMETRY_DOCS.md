# Workstream G: QA, Telemetry, and Documentation Hardening

Owner goal: make the revamp verifiable, observable, and maintainable.

## Owned Write Scope
- `backend/tests/**`
- `frontend/**` test scaffolding if introduced
- `README2.md` (or replacement readme if preferred)
- `docs/**` (non-workstream docs)

## Do Not Edit
- Core feature implementation logic unless required for testability hooks

## Tasks
1. Tighten weak tests:
   - replace permissive status assertions like `in (200, 422, 500, 502)` with deterministic expectations.
2. Add integration tests for:
   - workspace action orchestration
   - command registry parity
   - privacy guardrail (no large text in URL params)
3. Add lightweight telemetry hooks for:
   - action success/failure rate
   - time-to-first-answer
   - command invocation failure reasons
4. Update project docs:
   - current route counts/features
   - migration notes from legacy routes to workspace model
   - operator runbook for troubleshooting core services

## Acceptance Criteria
- Test suite catches key revamp regressions.
- README/docs reflect actual architecture and route model.
- Basic operational metrics can be inspected during pilot rollout.

## Validation
- Run backend test suite segments relevant to changed contracts.
- Verify docs match current code paths and endpoint names.

