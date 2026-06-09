"""Renovation Design Case subsystem.

Implements the Stage-1 contract from SPEC-HTTP-CASE.md:
- ingest: corpus library JSON -> Case payload (hdb_type enrichment, baseline snapshot)
- compliance: structural_wall_protected + walkway_accessibility rules
- design_agent: pinned-proposal + deterministic-planner Design Agent v0
- revise_loop: design -> compliance -> revise orchestration with N-failure escalation

See SPEC-HTTP-CASE.md sections 2-5 for the contract this implements.
"""

from .ingest import load_case_from_library
from .compliance import run_compliance, rule_structural_wall_protected, rule_walkway_accessibility
from .design_agent import DesignAgent
from .revise_loop import ReviseLoop, InvalidStateTransition

__all__ = [
    "load_case_from_library",
    "run_compliance",
    "rule_structural_wall_protected",
    "rule_walkway_accessibility",
    "DesignAgent",
    "ReviseLoop",
    "InvalidStateTransition",
]
