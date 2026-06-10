"""Stage-1 HTTP service for Renovation Design Cases.

This is the thin orchestration boundary from SPEC-HTTP-CASE.md section 4.
It intentionally stays separate from haus.chat_server: Maestro Case will call
these endpoints, while the viewer/chat server remains a local editing surface.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from threading import Lock
from typing import Any

import uvicorn
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from .design_agent import DesignAgent, PinnedProposalNotFound
from .ingest import load_case_from_library, touch
from .revise_loop import (
    DEFAULT_MAX_REVISE_ATTEMPTS,
    InvalidStateTransition,
    patch_approval,
    step_compliance,
    step_design,
    step_revise,
)
from .vendor_handoff import VendorCacheError, VendorHandoffAgent, step_handoff


ERROR_STATUS = {
    "validation_failed": 400,
    "case_not_found": 404,
    "invalid_state_transition": 409,
    "internal_error": 500,
}


class CaseNotFound(Exception):
    """Raised when a request references an unknown case_id."""


class CaseStore:
    """Process-local Case storage for the Stage-1 demo service.

    SPEC-HTTP-CASE.md section 7 leaves persistence to the implementer and
    declares Stage 1 single-writer. A locked in-memory store is enough for
    the standalone demo and keeps the later Maestro wrapper simple.
    """

    def __init__(self) -> None:
        self._cases: dict[str, dict[str, Any]] = {}
        self._lock = Lock()

    def create(self, case: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._cases[str(case["case_id"])] = case
            return case

    def get(self, case_id: str) -> dict[str, Any]:
        with self._lock:
            try:
                return self._cases[case_id]
            except KeyError as exc:
                raise CaseNotFound(case_id) from exc

    def replace(self, case: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._cases[str(case["case_id"])] = case
            return case


def _error(
    code: str,
    message: str,
    *,
    hint: str | None = None,
    status_code: int | None = None,
) -> JSONResponse:
    payload: dict[str, Any] = {"error": {"code": code, "message": message}}
    if hint:
        payload["error"]["hint"] = hint
    return JSONResponse(payload, status_code or ERROR_STATUS.get(code, 500))


async def _read_json_body(request: Request, *, default: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = await request.body()
    if not raw:
        return dict(default or {})
    try:
        body = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("Request body must be valid JSON.") from exc
    if not isinstance(body, dict):
        raise ValueError("Request body must be a JSON object.")
    return body


def _get_store(request: Request) -> CaseStore:
    return request.app.state.case_store


def _get_agent(request: Request) -> DesignAgent:
    return request.app.state.design_agent


def _get_max_revise(request: Request) -> int:
    return request.app.state.max_revise


def _get_handoff_agent(request: Request) -> VendorHandoffAgent:
    return request.app.state.handoff_agent


def _response(case: dict[str, Any], status_code: int = 200) -> JSONResponse:
    return JSONResponse(copy.deepcopy(case), status_code=status_code)


def _case_id(request: Request) -> str:
    case_id = request.path_params.get("case_id")
    return str(case_id or "")


async def _create_case(request: Request) -> JSONResponse:
    try:
        body = await _read_json_body(request)
    except ValueError as exc:
        return _error("validation_failed", str(exc))

    floor_plan_ref = body.get("floor_plan_ref")
    brief = body.get("brief")
    if not isinstance(floor_plan_ref, str) or not floor_plan_ref.strip():
        return _error("validation_failed", "Missing required string field: floor_plan_ref.")
    if not isinstance(brief, dict):
        return _error("validation_failed", "Missing required object field: brief.")

    pinned_proposal_id = body.get("pinned_proposal_id")
    if pinned_proposal_id is not None and not isinstance(pinned_proposal_id, str):
        return _error("validation_failed", "pinned_proposal_id must be a string or null.")
    vendor_cache_key = body.get("vendor_cache_key")
    if vendor_cache_key is not None and not isinstance(vendor_cache_key, str):
        return _error("validation_failed", "vendor_cache_key must be a string or null.")

    try:
        case = load_case_from_library(
            floor_plan_ref,
            brief=brief,
            pinned_proposal_id=pinned_proposal_id,
            vendor_cache_key=vendor_cache_key,
        )
    except (FileNotFoundError, ValueError) as exc:
        return _error(
            "validation_failed",
            "Could not create Case from library JSON.",
            hint=str(exc),
        )
    except OSError as exc:
        return _error(
            "internal_error",
            "Could not read Case library JSON.",
            hint=str(exc),
        )

    case["design_status"] = "designing"
    touch(case)
    _get_store(request).create(case)
    return _response(case, status_code=201)


async def _read_case(request: Request) -> JSONResponse:
    try:
        case = _get_store(request).get(_case_id(request))
    except CaseNotFound:
        return _error("case_not_found", f"Case not found: {_case_id(request)}")
    return _response(case)


async def _design_case(request: Request) -> JSONResponse:
    try:
        body = await _read_json_body(request, default={})
        case = _get_store(request).get(_case_id(request))
    except ValueError as exc:
        return _error("validation_failed", str(exc))
    except CaseNotFound:
        return _error("case_not_found", f"Case not found: {_case_id(request)}")

    style_override = body.get("style_override")
    if style_override is not None:
        if not isinstance(style_override, str):
            return _error("validation_failed", "style_override must be a string.")
        case.setdefault("brief", {})["style_prompt"] = style_override

    try:
        case = step_design(case, _get_agent(request))
    except InvalidStateTransition as exc:
        return _error("invalid_state_transition", str(exc))
    except PinnedProposalNotFound as exc:
        return _error("internal_error", "Pinned proposal could not be loaded.", hint=str(exc))

    _get_store(request).replace(case)
    return _response(case)


async def _compliance_case(request: Request) -> JSONResponse:
    try:
        await _read_json_body(request, default={})
        case = _get_store(request).get(_case_id(request))
    except ValueError as exc:
        return _error("validation_failed", str(exc))
    except CaseNotFound:
        return _error("case_not_found", f"Case not found: {_case_id(request)}")

    try:
        case = step_compliance(case, max_revise=_get_max_revise(request))
    except InvalidStateTransition as exc:
        return _error("invalid_state_transition", str(exc))

    _get_store(request).replace(case)
    return _response(case)


async def _revise_case(request: Request) -> JSONResponse:
    try:
        body = await _read_json_body(request)
        case = _get_store(request).get(_case_id(request))
    except ValueError as exc:
        return _error("validation_failed", str(exc))
    except CaseNotFound:
        return _error("case_not_found", f"Case not found: {_case_id(request)}")

    findings = body.get("findings")
    if not isinstance(findings, list) or not all(isinstance(f, dict) for f in findings):
        return _error("validation_failed", "findings must be an array of finding objects.")
    increment_count = body.get("increment_count", True)
    if not isinstance(increment_count, bool):
        return _error("validation_failed", "increment_count must be a boolean when provided.")

    try:
        case = step_revise(
            case,
            findings=findings,
            design_agent=_get_agent(request),
            increment_count=increment_count,
        )
    except InvalidStateTransition as exc:
        return _error("invalid_state_transition", str(exc))
    except PinnedProposalNotFound as exc:
        return _error("internal_error", "Pinned proposal could not be loaded.", hint=str(exc))

    _get_store(request).replace(case)
    return _response(case)


async def _approval_case(request: Request) -> JSONResponse:
    try:
        body = await _read_json_body(request)
        case = _get_store(request).get(_case_id(request))
    except ValueError as exc:
        return _error("validation_failed", str(exc))
    except CaseNotFound:
        return _error("case_not_found", f"Case not found: {_case_id(request)}")

    decision = body.get("decision")
    reviewer = body.get("reviewer")
    notes = body.get("notes")
    if decision not in {"approved", "rejected", "sent_back"}:
        return _error("validation_failed", "decision must be approved, rejected, or sent_back.")
    if not isinstance(reviewer, str) or not reviewer.strip():
        return _error("validation_failed", "reviewer must be a non-empty string.")
    if notes is not None and not isinstance(notes, str):
        return _error("validation_failed", "notes must be a string or null.")

    try:
        case = patch_approval(case, decision=decision, reviewer=reviewer, notes=notes)
    except InvalidStateTransition as exc:
        return _error("invalid_state_transition", str(exc))

    _get_store(request).replace(case)
    return _response(case)


async def _handoff_case(request: Request) -> JSONResponse:
    try:
        body = await _read_json_body(request, default={})
        case = _get_store(request).get(_case_id(request))
    except ValueError as exc:
        return _error("validation_failed", str(exc))
    except CaseNotFound:
        return _error("case_not_found", f"Case not found: {_case_id(request)}")

    vendor_cache_key = body.get("vendor_cache_key")
    if vendor_cache_key is not None and not isinstance(vendor_cache_key, str):
        return _error("validation_failed", "vendor_cache_key must be a string or null.")
    vendor_id = body.get("vendor_id")
    if vendor_id is not None and not isinstance(vendor_id, str):
        return _error("validation_failed", "vendor_id must be a string or null.")

    try:
        case = step_handoff(
            case,
            handoff_agent=_get_handoff_agent(request),
            vendor_cache_key=vendor_cache_key,
            vendor_id=vendor_id,
        )
    except InvalidStateTransition as exc:
        return _error("invalid_state_transition", str(exc))
    except VendorCacheError as exc:
        return _error("internal_error", "Vendor cache could not be used.", hint=str(exc))

    _get_store(request).replace(case)
    return _response(case)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _default_proposals_dir() -> Path | None:
    configured = os.environ.get("HAUS_CASE_PROPOSALS_DIR")
    if configured:
        return Path(configured)
    default = Path("tests/fixtures/proposals")
    return default if default.exists() else None


def _default_vendor_cache_dir() -> Path | None:
    configured = os.environ.get("HAUS_VENDOR_CACHE_DIR")
    if configured:
        return Path(configured)
    fixture = Path("tests/fixtures/vendors")
    if fixture.exists():
        return fixture
    runtime = Path.home() / ".haus" / "vendors"
    return runtime if runtime.exists() else None


def _default_handoff_root() -> Path:
    configured = os.environ.get("HAUS_HANDOFF_ROOT")
    if configured:
        return Path(configured)
    return Path.home() / ".haus" / "handoffs"


def create_app(
    *,
    proposals_dir: str | Path | None = None,
    vendor_cache_dir: str | Path | None = None,
    handoff_root: str | Path | None = None,
    max_revise: int | None = None,
    design_mode: str | None = None,
    design_provider: str | None = None,
    design_model: str | None = None,
    cache_live_proposals: bool | None = None,
    store: CaseStore | None = None,
) -> Starlette:
    app = Starlette(
        routes=[
            Route("/case", _create_case, methods=["POST"]),
            Route("/case/{case_id}", _read_case, methods=["GET"]),
            Route("/case/{case_id}/design", _design_case, methods=["POST"]),
            Route("/case/{case_id}/compliance", _compliance_case, methods=["POST"]),
            Route("/case/{case_id}/revise", _revise_case, methods=["POST"]),
            Route("/case/{case_id}/approval", _approval_case, methods=["PATCH"]),
            Route("/case/{case_id}/handoff", _handoff_case, methods=["POST"]),
        ]
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["*"],
    )
    resolved_proposals = Path(proposals_dir) if proposals_dir is not None else _default_proposals_dir()
    resolved_vendor_cache = (
        Path(vendor_cache_dir) if vendor_cache_dir is not None else _default_vendor_cache_dir()
    )
    resolved_handoff_root = Path(handoff_root) if handoff_root is not None else _default_handoff_root()
    app.state.case_store = store or CaseStore()
    app.state.design_agent = DesignAgent(
        proposals_dir=resolved_proposals,
        mode=design_mode,
        provider=design_provider,
        model=design_model,
        cache_live_proposals=cache_live_proposals,
    )
    app.state.handoff_agent = VendorHandoffAgent(
        vendor_cache_dir=resolved_vendor_cache,
        handoff_root=resolved_handoff_root,
    )
    app.state.max_revise = max_revise or _env_int(
        "MAX_REVISE_ATTEMPTS",
        DEFAULT_MAX_REVISE_ATTEMPTS,
    )
    return app


def run_server(
    *,
    host: str = "127.0.0.1",
    port: int = 8090,
    proposals_dir: str | Path | None = None,
    vendor_cache_dir: str | Path | None = None,
    handoff_root: str | Path | None = None,
    max_revise: int | None = None,
    design_mode: str | None = None,
    design_provider: str | None = None,
    design_model: str | None = None,
    cache_live_proposals: bool | None = None,
) -> None:
    if proposals_dir is not None:
        os.environ["HAUS_CASE_PROPOSALS_DIR"] = str(proposals_dir)
    if vendor_cache_dir is not None:
        os.environ["HAUS_VENDOR_CACHE_DIR"] = str(vendor_cache_dir)
    if handoff_root is not None:
        os.environ["HAUS_HANDOFF_ROOT"] = str(handoff_root)
    if max_revise is not None:
        os.environ["MAX_REVISE_ATTEMPTS"] = str(max_revise)
    if design_mode is not None:
        os.environ["HAUS_CASE_DESIGN_MODE"] = design_mode
    if design_provider is not None:
        os.environ["HAUS_CASE_LLM_PROVIDER"] = design_provider
    if design_model is not None:
        os.environ["HAUS_CASE_LLM_MODEL"] = design_model
    if cache_live_proposals is not None:
        os.environ["HAUS_CASE_CACHE_LIVE_PROPOSALS"] = "1" if cache_live_proposals else "0"
    uvicorn.run(
        "haus.case.http_server:_reload_app",
        factory=True,
        host=host,
        port=port,
        reload=False,
    )


def _reload_app() -> Starlette:
    return create_app()
