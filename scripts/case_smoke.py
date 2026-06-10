#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_BRIEF = {
    "flat_type": "3-room BTO",
    "household_size": 2,
    "style_prompt": "minimalist renovation concept",
    "constraints": ["preserve HDB structural and shelter walls"],
    "must_keep_rooms": [],
}


class SmokeFailure(RuntimeError):
    pass


def _json_request(
    base_url: str,
    method: str,
    path: str,
    *,
    token: str | None,
    payload: dict[str, Any] | None = None,
    timeout: float = 20.0,
) -> tuple[int, dict[str, Any]]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = Request(base_url.rstrip("/") + path, data=data, method=method)
    req.add_header("Accept", "application/json")
    if payload is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")

    try:
        with urlopen(req, timeout=timeout) as res:
            raw = res.read().decode("utf-8")
            body = json.loads(raw) if raw else {}
            if not isinstance(body, dict):
                raise SmokeFailure(f"{method} {path} returned non-object JSON")
            return int(res.status), body
    except HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            body = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            body = {"error": {"message": raw}}
        if not isinstance(body, dict):
            body = {"error": {"message": raw}}
        return int(exc.code), body
    except URLError as exc:
        raise SmokeFailure(f"{method} {path} failed: {exc}") from exc


def _require_status(label: str, status: int, expected: set[int], body: dict[str, Any]) -> None:
    if status not in expected:
        raise SmokeFailure(f"{label}: expected HTTP {sorted(expected)}, got {status}: {json.dumps(body)[:500]}")


def _require_case(label: str, body: dict[str, Any], expected_status: str | None = None) -> dict[str, Any]:
    case_id = body.get("case_id")
    design_status = body.get("design_status")
    if not isinstance(case_id, str) or not case_id:
        raise SmokeFailure(f"{label}: response missing case_id")
    if not isinstance(design_status, str):
        raise SmokeFailure(f"{label}: response missing design_status")
    if expected_status is not None and design_status != expected_status:
        raise SmokeFailure(f"{label}: expected design_status={expected_status}, got {design_status}")
    return body


def _print_step(label: str, case: dict[str, Any]) -> None:
    findings = case.get("compliance_findings")
    finding_count = len(findings) if isinstance(findings, list) else 0
    errors = 0
    if isinstance(findings, list):
        errors = sum(1 for finding in findings if isinstance(finding, dict) and finding.get("severity") == "error")
    handoff = case.get("vendor_handoff")
    packet = ""
    if isinstance(handoff, dict) and handoff.get("packet_uri"):
        packet = f" packet={handoff['packet_uri']}"
    print(
        f"{label}: status={case.get('design_status')} revise_count={case.get('revise_count', 0)} "
        f"findings={finding_count} errors={errors}{packet}"
    )


def _load_brief(raw: str | None) -> dict[str, Any]:
    if raw is None:
        return dict(DEFAULT_BRIEF)
    path = Path(raw)
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        data = json.loads(raw)
    if not isinstance(data, dict):
        raise SmokeFailure("brief must be a JSON object or a path to one")
    return data


def run(args: argparse.Namespace) -> dict[str, Any]:
    token = args.token if args.token is not None else os.environ.get("HAUS_CASE_API_TOKEN")
    brief = _load_brief(args.brief)

    status, body = _json_request(
        args.base_url,
        "POST",
        "/case",
        token=token,
        payload={
            "floor_plan_ref": str(args.fixture),
            "brief": brief,
            "pinned_proposal_id": args.pinned,
            "vendor_cache_key": args.vendor_cache_key,
        },
    )
    _require_status("create", status, {201}, body)
    case = _require_case("create", body, "designing")
    case_id = str(case["case_id"])
    _print_step("create", case)

    status, body = _json_request(args.base_url, "POST", f"/case/{case_id}/design", token=token, payload={})
    _require_status("design", status, {200}, body)
    case = _require_case("design", body, "compliance_pending")
    _print_step("design", case)

    compliance_runs = 0
    while True:
        compliance_runs += 1
        if compliance_runs > args.max_compliance_runs:
            raise SmokeFailure(f"compliance loop exceeded {args.max_compliance_runs} runs")
        status, body = _json_request(args.base_url, "POST", f"/case/{case_id}/compliance", token=token, payload={})
        _require_status(f"compliance#{compliance_runs}", status, {200}, body)
        case = _require_case(f"compliance#{compliance_runs}", body)
        _print_step(f"compliance#{compliance_runs}", case)

        if case["design_status"] == "revising":
            findings = case.get("compliance_findings")
            if not isinstance(findings, list):
                raise SmokeFailure("revising case missing compliance_findings array")
            status, body = _json_request(
                args.base_url,
                "POST",
                f"/case/{case_id}/revise",
                token=token,
                payload={"findings": findings},
            )
            _require_status(f"revise#{case.get('revise_count', 0) + 1}", status, {200}, body)
            case = _require_case("revise", body)
            _print_step(f"revise#{case.get('revise_count', 0)}", case)
            if case["design_status"] == "awaiting_human_approval":
                break
            if case["design_status"] != "compliance_pending":
                raise SmokeFailure(f"revise returned unexpected status {case['design_status']}")
            continue

        if case["design_status"] == "awaiting_human_approval":
            break
        raise SmokeFailure(f"compliance returned unexpected status {case['design_status']}")

    if not args.skip_approval:
        status, body = _json_request(
            args.base_url,
            "PATCH",
            f"/case/{case_id}/approval",
            token=token,
            payload={"decision": args.approval_decision, "reviewer": args.reviewer, "notes": args.approval_notes},
        )
        _require_status("approval", status, {200}, body)
        expected = "approved" if args.approval_decision == "approved" else case["design_status"]
        case = _require_case("approval", body, expected)
        _print_step("approval", case)

    if case.get("design_status") == "approved" and not args.skip_handoff:
        payload: dict[str, Any] = {"vendor_cache_key": args.vendor_cache_key}
        if args.vendor_id:
            payload["vendor_id"] = args.vendor_id
        status, body = _json_request(args.base_url, "POST", f"/case/{case_id}/handoff", token=token, payload=payload)
        _require_status("handoff", status, {200}, body)
        case = _require_case("handoff", body, "handoff_complete")
        if not isinstance(case.get("vendor_handoff"), dict):
            raise SmokeFailure("handoff response missing vendor_handoff")
        _print_step("handoff", case)

    return case


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Smoke-test the Haus Case HTTP service.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8090")
    parser.add_argument("--fixture", type=Path, default=Path("corpus/library/3.json"))
    parser.add_argument("--pinned", default="demo_3room_remove_wall_28")
    parser.add_argument("--brief", default=None, help="Brief JSON string or path")
    parser.add_argument("--vendor-cache-key", default="demo_hdb_renovation")
    parser.add_argument("--vendor-id", default=None)
    parser.add_argument("--token", default=None, help="Bearer token; defaults to HAUS_CASE_API_TOKEN")
    parser.add_argument("--max-compliance-runs", type=int, default=8)
    parser.add_argument("--reviewer", default="coordinator_smoke")
    parser.add_argument("--approval-notes", default="Approved by local smoke test.")
    parser.add_argument("--approval-decision", choices=("approved", "rejected", "sent_back"), default="approved")
    parser.add_argument("--skip-approval", action="store_true")
    parser.add_argument("--skip-handoff", action="store_true")
    parser.add_argument("--print-json", action="store_true")
    args = parser.parse_args(argv)

    try:
        case = run(args)
    except (SmokeFailure, json.JSONDecodeError) as exc:
        print(f"smoke failed: {exc}", file=sys.stderr)
        return 1

    if args.print_json:
        print(json.dumps(case, indent=2))
    print("smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
