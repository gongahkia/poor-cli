from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .agents import _provider_for_agent
from .artifacts import write_review_artifact, write_verify_artifact
from .config import explain_route, load_config
from .cost import BudgetLedger
from .fusion import FusionRouteError, normalize_fusion_payload, route_uses_fusion, validate_fusion_route, write_fusion_artifact
from .models import AgentInfo
from .providers import CachedReplayProvider, ProviderRequest
from .sandbox import SandboxDenied, validate_shell_command
from .store import RunStore


class LaneError(RuntimeError):
    pass


REVIEW_SYSTEM_PROMPT = (
    "Return only JSON with fields status, findings, recommendation. "
    "Findings use severity,file,line,evidence,recommendation. Be critical and concise."
)


def review_run(
    store: RunStore,
    run_id: str,
    *,
    allow_expensive_router: bool = False,
    suppressions: list[dict[str, str]] | None = None,
) -> int:
    run = store.get_run(run_id)
    repo = Path(str(run["repo_path"]))
    config = load_config(repo)
    route = explain_route(config, "review run artifacts", role="reviewer")
    route = _resolve_review_route(store, run_id, config, route, allow_expensive_router)
    agent = _agent_for_route(config, route)
    store.append_event(run_id, "review.started", {"route": route})
    prompt = _review_prompt(store, run_id)
    provider = CachedReplayProvider(store, run_id, _provider_for_agent(agent))
    response = provider.call(
        ProviderRequest(
            provider=agent.provider,
            model=agent.default_model or "",
            prompt=prompt,
            system_prompt=REVIEW_SYSTEM_PROMPT,
            params=_review_params(route),
        )
    )
    if route.get("fusion", {}).get("enabled"):
        fusion = normalize_fusion_payload(response.content, response.raw)
        fusion["fallback_used"] = False
        write_fusion_artifact(store, run_id, "review", fusion)
    try:
        payload = _normalize_review(json.loads(response.content), suppressions or [])
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        payload = {
            "schema_version": "poor-cli-review-v1",
            "status": "failed",
            "reviewer": asdict(agent),
            "findings": [],
            "suppressions": suppressions or [],
            "recommendation": "reject",
            "error": str(exc),
            "source_artifacts": _artifact_paths(store, run_id),
            "cost": BudgetLedger.load(store, run_id).totals(),
        }
        write_review_artifact(store, run_id, payload)
        store.append_event(run_id, "review.failed", {"error": str(exc)})
        return 1
    payload.update(
        {
            "reviewer": asdict(agent),
            "source_artifacts": _artifact_paths(store, run_id),
            "cost": BudgetLedger.load(store, run_id).totals(),
        }
    )
    write_review_artifact(store, run_id, payload)
    event = "review.rejected" if payload["recommendation"] == "reject" else "review.completed"
    store.append_event(run_id, event, {"findings": len(payload["findings"]), "recommendation": payload["recommendation"]})
    return 2 if payload["recommendation"] == "reject" else 0


def verify_run(store: RunStore, run_id: str, *, commands: list[str] | None = None) -> int:
    run = store.get_run(run_id)
    repo = Path(str(run["repo_path"]))
    selected = commands or [cmd for task in store.list_tasks(run_id) for cmd in (task.get("validation") or [])]
    store.append_event(run_id, "verify.started", {"command_count": len(selected)})
    rows = []
    for command in selected:
        rows.append(_run_verify_command(store, run_id, repo, str(command)))
    passed = bool(rows) and all(row["returncode"] == 0 for row in rows)
    payload = {
        "schema_version": "poor-cli-verify-v1",
        "status": "passed" if passed else "failed",
        "summary": f"{sum(1 for row in rows if row['returncode'] == 0)}/{len(rows)} commands passed",
        "commands": rows,
        "benchmark_deltas": {},
        "pass": passed,
        "cost": BudgetLedger.load(store, run_id).totals(),
    }
    write_verify_artifact(store, run_id, payload)
    store.append_event(run_id, "verify.completed" if passed else "verify.failed", {"pass": passed, "command_count": len(rows)})
    return 0 if passed else 1


def _run_verify_command(store: RunStore, run_id: str, repo: Path, command: str) -> dict[str, Any]:
    try:
        validate_shell_command(repo, command)
    except SandboxDenied as exc:
        row = {"command": command, "returncode": 126, "stdout": "", "stderr": str(exc), "sandbox_denied": True}
        store.append_event(run_id, "verify.command.completed", row)
        return row
    result = subprocess.run(command, cwd=repo, shell=True, text=True, capture_output=True, timeout=300, check=False)
    row = {
        "command": command,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "sandbox_denied": False,
    }
    store.append_event(run_id, "verify.command.completed", row)
    return row


def _agent_for_route(config: dict[str, Any], route: dict[str, Any]) -> AgentInfo:
    providers = config.get("providers")
    profile_id = str(route.get("profile") or "")
    profile = providers.get(profile_id) if isinstance(providers, dict) else None
    if not isinstance(profile, dict):
        raise LaneError("reviewer route has no configured provider")
    model = str(route.get("model") or "")
    models = profile.get("models")
    if not model and isinstance(models, list) and models:
        model = str(models[0])
    if not model:
        raise LaneError("reviewer route has no model")
    raw_auth = profile.get("auth")
    auth = raw_auth if isinstance(raw_auth, dict) else {}
    return AgentInfo(
        agent_id=f"agent_reviewer_{profile_id}",
        name=profile_id,
        command=str(profile.get("base_url") or profile.get("kind") or ""),
        version=f"{profile.get('kind')}:{model}",
        provider=str(profile.get("kind") or ""),
        capabilities=["review", "tools"],
        default_model=model,
        cost_profile={"auth_env": str(auth.get("env") or "")},
        invocation_adapter="provider",
    )


def _check_router_budget(config: dict[str, Any], route: dict[str, Any], allow_expensive_router: bool) -> None:
    profile = (config.get("providers") or {}).get(str(route.get("profile") or ""))
    if not isinstance(profile, dict):
        return
    kind = str(profile.get("kind") or "")
    model = str(route.get("model") or "")
    if kind == "openrouter" and "fusion" in model.lower() and not allow_expensive_router and not route.get("max_cost_usd"):
        raise LaneError("Fusion review requires --allow-expensive-router or routes.reviewer.max_cost_usd")


def _resolve_review_route(
    store: RunStore, run_id: str, config: dict[str, Any], route: dict[str, Any], allow_expensive_router: bool
) -> dict[str, Any]:
    providers = config.get("providers") if isinstance(config.get("providers"), dict) else {}
    profile = providers.get(str(route.get("profile") or "")) if isinstance(providers, dict) else {}
    if not route_uses_fusion(profile if isinstance(profile, dict) else {}, route):
        return route
    check = validate_fusion_route(config, "reviewer", route, allow_expensive_router=allow_expensive_router)
    if check.reason:
        if not check.fallback or not check.fallback.get("profile"):
            raise LaneError(check.reason)
        fallback = dict(route)
        fallback["profile"] = check.fallback["profile"]
        if check.fallback.get("model"):
            fallback["model"] = check.fallback["model"]
        fallback["fusion"] = {"enabled": False, "fallback_used": True, "reason": check.reason}
        store.append_event(run_id, "fusion.fallback", {"reason": check.reason, "fallback": check.fallback})
        return fallback
    resolved = dict(route)
    resolved["fusion"] = {"enabled": True, "params": check.params or {}}
    store.append_event(run_id, "fusion.selected", {"role": "reviewer", "params": check.params or {}})
    return resolved


def _review_params(route: dict[str, Any]) -> dict[str, Any]:
    params: dict[str, Any] = {"json_schema": _review_schema()}
    fusion = route.get("fusion")
    if isinstance(fusion, dict) and fusion.get("enabled"):
        params["fusion"] = fusion.get("params") or {}
    return params


def _review_prompt(store: RunStore, run_id: str) -> str:
    run = store.get_run(run_id)
    paths = _artifact_paths(store, run_id)
    chunks = [f"Run: {run_id}", f"Goal: {run['user_goal']}", "Review these artifacts and return JSON."]
    for path in paths:
        if not (path.endswith("PATCH.diff") or path.endswith("RESULT.md") or path == "PLAN.md"):
            continue
        artifact_path = store.root / "runs" / run_id / "artifacts" / path
        if artifact_path.exists():
            chunks.append(f"\n## {path}\n{artifact_path.read_text(encoding='utf-8')[:12000]}")
    return "\n".join(chunks)


def _normalize_review(payload: dict[str, Any], suppressions: list[dict[str, str]]) -> dict[str, Any]:
    findings = []
    suppressed = {row["id"]: row for row in suppressions if row.get("id")}
    for raw in payload.get("findings") or []:
        if not isinstance(raw, dict):
            continue
        finding = {
            "id": str(raw.get("id") or _finding_id(raw)),
            "severity": str(raw.get("severity") or "medium"),
            "file": str(raw.get("file") or ""),
            "line": int(raw.get("line") or 0),
            "evidence": str(raw.get("evidence") or ""),
            "recommendation": str(raw.get("recommendation") or ""),
            "suppressed": False,
        }
        if finding["id"] in suppressed:
            finding["suppressed"] = True
            finding["suppression"] = suppressed[finding["id"]]
        findings.append(finding)
    active = [row for row in findings if not row["suppressed"]]
    recommendation = str(payload.get("recommendation") or ("reject" if active else "accept")).lower()
    if recommendation not in {"accept", "reject"}:
        recommendation = "reject" if active else "accept"
    if not active:
        recommendation = "accept"
    return {
        "schema_version": "poor-cli-review-v1",
        "status": "rejected" if recommendation == "reject" else "accepted",
        "finding_fields": ["severity", "file", "line", "evidence", "recommendation"],
        "findings": findings,
        "suppressions": suppressions,
        "recommendation": recommendation,
    }


def _artifact_paths(store: RunStore, run_id: str) -> list[str]:
    base = store.root / "runs" / run_id / "artifacts"
    return [str(path.relative_to(base)) for path in sorted(base.rglob("*")) if path.is_file()] if base.exists() else []


def _finding_id(raw: dict[str, Any]) -> str:
    text = "|".join(str(raw.get(key) or "") for key in ("severity", "file", "line", "evidence", "recommendation"))
    return "rev_" + hashlib.sha256(text.encode()).hexdigest()[:12]


def _review_schema() -> dict[str, Any]:
    return {
        "name": "PoorCliReview",
        "schema": {
            "type": "object",
            "properties": {
                "findings": {"type": "array"},
                "recommendation": {"type": "string"},
            },
            "required": ["findings", "recommendation"],
            "additionalProperties": True,
        },
    }


def suppression_rows(ids: list[str], reason: str | None, expires: str | None) -> list[dict[str, str]]:
    if ids and not reason:
        raise LaneError("--reason is required with --suppress-finding")
    return [{"id": item, "reason": reason or "", "expires": expires or ""} for item in ids]
