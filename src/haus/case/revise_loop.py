"""Revise loop + N-failure escalation per SPEC-HTTP-CASE.md sections 4.2 and 4.4 + Appendix A.

Three step functions matching the three mutating HTTP endpoints; orchestrator class
ReviseLoop binds a DesignAgent + N together for end-to-end runs and tests.

Status transitions (the source of truth is SPEC Appendix A — the round-trip table —
which slightly tightens the loose-language paragraph in section 4.2):

  step_design     : <intake|designing|revising> -> compliance_pending
  step_compliance : compliance_pending -> revising | awaiting_human_approval
  step_revise     : revising -> compliance_pending      (always, when increment runs design)
  patch_approval  : awaiting_human_approval -> approved | rejected   (Stage-1 stub; SPEC 4.4)

Escalation rule (SPEC 4.4):
- /compliance moves to awaiting_human_approval when (a) no error findings, OR
  (b) errors exist AND revise_count >= N.  In case (b), approval_state.escalation_reason
  is populated with the N-exhaustion message.
"""
from __future__ import annotations

from typing import Any, Sequence

from .compliance import has_errors, run_compliance
from .design_agent import DesignAgent
from .ingest import touch


DEFAULT_MAX_REVISE_ATTEMPTS = 3


class InvalidStateTransition(Exception):
    """Raised when a mutating step is called against the wrong design_status (SPEC 4.2/4.3)."""


_DESIGN_PRESTATES = {"intake", "designing", "revising"}
_COMPLIANCE_PRESTATES = {"compliance_pending"}
_REVISE_PRESTATES = {"revising"}
_APPROVAL_PRESTATES = {"awaiting_human_approval"}


def _require(case: dict[str, Any], allowed: set[str], op: str) -> None:
    status = case.get("design_status")
    if status not in allowed:
        raise InvalidStateTransition(
            f"{op} requires design_status in {sorted(allowed)}, got {status!r}"
        )


def step_design(case: dict[str, Any], design_agent: DesignAgent) -> dict[str, Any]:
    """POST /case/{id}/design. Pre-state intake|designing|revising -> compliance_pending."""
    _require(case, _DESIGN_PRESTATES, "design")
    case["design_status"] = "designing"  # transient marker during the call
    case = design_agent.propose(case)
    # design_agent.propose already sets compliance_pending and touches updated_at
    return case


def step_compliance(
    case: dict[str, Any],
    *,
    max_revise: int = DEFAULT_MAX_REVISE_ATTEMPTS,
) -> dict[str, Any]:
    """POST /case/{id}/compliance. Idempotent run of all rules; sets status per escalation rule."""
    _require(case, _COMPLIANCE_PRESTATES, "compliance")
    findings = run_compliance(case)
    case["compliance_findings"] = findings
    if not has_errors(findings):
        case["design_status"] = "awaiting_human_approval"
        # clean-path approval_state init: no escalation reason
        case["approval_state"] = _init_approval_state(escalation_reason=None)
    elif case.get("revise_count", 0) >= max_revise:
        case["design_status"] = "awaiting_human_approval"
        case["approval_state"] = _init_approval_state(
            escalation_reason=(
                f"Auto-revise exhausted (revise_count={case.get('revise_count', 0)}, N={max_revise}) "
                f"on rule(s): {sorted({f['rule_id'] for f in findings if f.get('severity') == 'error'})}."
            ),
        )
    else:
        case["design_status"] = "revising"
    touch(case)
    return case


def step_revise(
    case: dict[str, Any],
    *,
    findings: Sequence[dict[str, Any]],
    design_agent: DesignAgent,
    increment_count: bool = True,
) -> dict[str, Any]:
    """POST /case/{id}/revise. Increments counter, re-runs design with findings as hints.

    Per SPEC Appendix A, this always returns compliance_pending after a successful design
    re-run, even when increment pushes revise_count to N. Escalation happens in the next
    /compliance call when errors persist AND revise_count >= N.
    """
    _require(case, _REVISE_PRESTATES, "revise")
    if increment_count:
        case["revise_count"] = case.get("revise_count", 0) + 1
    hints: list[dict[str, Any]] = []
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        hint = finding.get("machine_hint")
        if isinstance(hint, dict):
            hints.append(hint)
    case = design_agent.propose(case, hints=hints)
    return case


def patch_approval(
    case: dict[str, Any],
    *,
    decision: str,
    reviewer: str,
    notes: str | None = None,
) -> dict[str, Any]:
    """Stage-1 PATCH stub for the human-approval transition (SPEC 4.4).

    Stage 2 replaces this with Action Center wiring; the contract surface
    (approval_state shape, status transition) stays the same.
    """
    _require(case, _APPROVAL_PRESTATES, "approval")
    if decision not in {"approved", "rejected", "sent_back"}:
        raise ValueError(f"decision must be approved/rejected/sent_back, got {decision!r}")
    from datetime import datetime, timezone
    approval = case.get("approval_state") or _init_approval_state(escalation_reason=None)
    approval["decision"] = decision
    approval["reviewer"] = reviewer
    approval["decided_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if notes is not None:
        approval["notes"] = notes
    case["approval_state"] = approval
    if decision == "approved":
        case["design_status"] = "approved"
    elif decision == "rejected":
        case["design_status"] = "rejected"
    # sent_back keeps status as awaiting_human_approval (reviewer asks for another pass);
    # Stage 2 may add an explicit re-design transition.
    touch(case)
    return case


def _init_approval_state(*, escalation_reason: str | None) -> dict[str, Any]:
    return {
        "decision": "pending",
        "reviewer": None,
        "decided_at": None,
        "notes": None,
        "escalation_reason": escalation_reason,
    }


class ReviseLoop:
    """Orchestrator binding a DesignAgent + N for end-to-end demo / test runs.

    Mirrors the HTTP endpoint surface so the eventual web layer can be a thin wrapper.
    """

    def __init__(
        self,
        design_agent: DesignAgent,
        *,
        max_revise: int = DEFAULT_MAX_REVISE_ATTEMPTS,
    ) -> None:
        self.design_agent = design_agent
        self.max_revise = max_revise

    def design(self, case: dict[str, Any]) -> dict[str, Any]:
        return step_design(case, self.design_agent)

    def compliance(self, case: dict[str, Any]) -> dict[str, Any]:
        return step_compliance(case, max_revise=self.max_revise)

    def revise(
        self,
        case: dict[str, Any],
        *,
        findings: Sequence[dict[str, Any]] | None = None,
        increment_count: bool = True,
    ) -> dict[str, Any]:
        if findings is None:
            raw_findings = case.get("compliance_findings", [])
            findings = raw_findings if isinstance(raw_findings, list) else []
        return step_revise(
            case,
            findings=findings,
            design_agent=self.design_agent,
            increment_count=increment_count,
        )

    def run_to_human(self, case: dict[str, Any]) -> dict[str, Any]:
        """Drive the loop until design_status == 'awaiting_human_approval'.

        Demo helper. Real Stage-2 Maestro orchestrates these steps externally; here
        we just chain them so a test or a CLI can produce the Appendix-A round-trip
        without manually calling each step.
        """
        case = self.design(case)
        while True:
            case = self.compliance(case)
            if case["design_status"] == "awaiting_human_approval":
                return case
            if case["design_status"] != "revising":
                raise RuntimeError(
                    f"Unexpected status after compliance: {case['design_status']!r}"
                )
            case = self.revise(case)
