from __future__ import annotations

import json
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


class PromptPackError(RuntimeError):
    pass


@dataclass(frozen=True)
class PromptPack:
    id: str
    version: str
    license: str
    source_url: str
    scope: str
    roles: list[str]
    template: str
    arguments: list[str]
    provenance_status: str

    @property
    def token_estimate(self) -> int:
        return max(1, len(self.template.encode("utf-8")) // 4)


BUILTIN_PACKS: dict[str, PromptPack] = {
    "planner.default": PromptPack(
        "planner.default",
        "1.0.0",
        "MIT",
        "local:poor-cli",
        "planning",
        ["planner"],
        "Return a scoped JSON plan. State assumptions, risks, tasks, validation, and routing. Prefer small sequential tasks.",
        ["goal", "repo", "agents"],
        "local-authored",
    ),
    "executor.native": PromptPack(
        "executor.native",
        "1.0.0",
        "MIT",
        "local:poor-cli",
        "execution",
        ["executor"],
        "Use tools for repo I/O. Make the smallest correct change. Report validation and blockers.",
        ["goal", "task", "context"],
        "local-authored",
    ),
    "reviewer.anti_sycophancy": PromptPack(
        "reviewer.anti_sycophancy",
        "1.0.0",
        "MIT",
        "local:poor-cli",
        "review",
        ["reviewer"],
        "Review critically. Check assumptions, contrary evidence, missing tests, security risk, "
        "and benchmark-gated claims. Do not agree by default.",
        ["artifacts"],
        "local-authored",
    ),
    "verifier.default": PromptPack(
        "verifier.default",
        "1.0.0",
        "MIT",
        "local:poor-cli",
        "verification",
        ["verifier"],
        "Run configured validation. Report exact commands, pass/fail, benchmark deltas, and unresolved blockers.",
        ["commands"],
        "local-authored",
    ),
    "graph.navigator": PromptPack(
        "graph.navigator",
        "1.0.0",
        "MIT",
        "local:poor-cli",
        "context",
        ["planner", "executor", "graph_navigator"],
        "Prefer find_symbol, definition_of, callers_of, imports_of, and subgraph before broad grep when parser support exists.",
        ["goal", "graph_context"],
        "local-authored",
    ),
}


def load_prompt_packs(repo: Path | None = None) -> dict[str, PromptPack]:
    packs = dict(BUILTIN_PACKS)
    path = (repo or Path.cwd()) / ".poor-cli" / "prompt-packs.toml"
    if path.exists():
        for pack in _read_pack_file(path):
            packs[pack.id] = pack
    return packs


def pack_rows(repo: Path | None = None) -> list[dict[str, Any]]:
    return [
        {**asdict(pack), "token_estimate": pack.token_estimate}
        for pack in sorted(load_prompt_packs(repo).values(), key=lambda item: item.id)
    ]


def selected_pack_id(config: dict[str, Any], role: str) -> str:
    route = (config.get("routes") or {}).get(role)
    if isinstance(route, dict) and route.get("prompt_pack"):
        return str(route["prompt_pack"])
    defaults = {
        "planner": "planner.default",
        "executor": "executor.native",
        "reviewer": "reviewer.anti_sycophancy",
        "verifier": "verifier.default",
        "graph_navigator": "graph.navigator",
    }
    return defaults.get(role, "")


def prompt_prefix(config: dict[str, Any], role: str, repo: Path | None = None) -> str:
    pack_id = selected_pack_id(config, role)
    if not pack_id:
        return ""
    packs = load_prompt_packs(repo)
    if pack_id not in packs:
        raise PromptPackError(f"prompt pack not found: {pack_id}")
    pack = packs[pack_id]
    if role not in pack.roles:
        raise PromptPackError(f"prompt pack {pack_id} does not support role {role}")
    return pack.template


def validate_prompt_pack_payload(payload: dict[str, Any], *, source: str = "<prompt-pack>") -> PromptPack:
    required = ("id", "version", "license", "source_url", "scope", "roles", "template", "arguments", "provenance_status")
    missing = [key for key in required if key not in payload or payload[key] in ("", None)]
    if missing:
        raise PromptPackError(f"{source} missing fields: {', '.join(missing)}")
    roles = payload["roles"]
    args = payload["arguments"]
    if not isinstance(roles, list) or not all(isinstance(item, str) and item for item in roles):
        raise PromptPackError(f"{source} roles must be a string list")
    if not isinstance(args, list) or not all(isinstance(item, str) for item in args):
        raise PromptPackError(f"{source} arguments must be a string list")
    provenance = str(payload["provenance_status"])
    if provenance not in {"local-authored", "user-provided", "permissive-source-summary"}:
        raise PromptPackError(f"{source} has disallowed provenance status: {provenance}")
    return PromptPack(
        id=str(payload["id"]),
        version=str(payload["version"]),
        license=str(payload["license"]),
        source_url=str(payload["source_url"]),
        scope=str(payload["scope"]),
        roles=[str(item) for item in roles],
        template=str(payload["template"]),
        arguments=[str(item) for item in args],
        provenance_status=provenance,
    )


def prompt_efficiency_report(before: str, after: str) -> dict[str, Any]:
    before_bytes = len(before.encode("utf-8"))
    after_bytes = len(after.encode("utf-8"))
    return {
        "schema_version": "poor-cli-prompt-efficiency-v1",
        "before_bytes": before_bytes,
        "after_bytes": after_bytes,
        "delta_bytes": after_bytes - before_bytes,
        "before_token_estimate": max(1, before_bytes // 4),
        "after_token_estimate": max(1, after_bytes // 4),
    }


def handle_prompt_command(args: Any, repo: Path | None = None) -> int:
    if args.prompt_command == "packs":
        rows = pack_rows(repo)
        if args.json:
            print(json.dumps({"packs": rows}, indent=2, sort_keys=True))
            return 0
        for row in rows:
            print(f"{row['id']}\t{','.join(row['roles'])}\t{row['license']}\t{row['token_estimate']}")
        return 0
    if args.prompt_command == "efficiency":
        before = Path(args.before).read_text(encoding="utf-8")
        after = Path(args.after).read_text(encoding="utf-8")
        print(json.dumps(prompt_efficiency_report(before, after), indent=2, sort_keys=True))
        return 0
    raise RuntimeError("missing prompt command")


def add_prompt_parser(subparsers: Any) -> None:
    prompt = subparsers.add_parser("prompt")
    prompt_sub = prompt.add_subparsers(dest="prompt_command")
    prompt_packs = prompt_sub.add_parser("packs")
    prompt_packs.add_argument("--json", action="store_true")
    prompt_eff = prompt_sub.add_parser("efficiency")
    prompt_eff.add_argument("--before", required=True)
    prompt_eff.add_argument("--after", required=True)


def _read_pack_file(path: Path) -> list[PromptPack]:
    data = json.loads(path.read_text(encoding="utf-8")) if path.suffix == ".json" else tomllib.loads(path.read_text(encoding="utf-8"))
    raw = data.get("packs") if isinstance(data, dict) else None
    if isinstance(raw, dict):
        return [validate_prompt_pack_payload({"id": key, **value}, source=f"{path}:{key}") for key, value in raw.items()]
    if isinstance(raw, list):
        return [validate_prompt_pack_payload(value, source=str(path)) for value in raw if isinstance(value, dict)]
    raise PromptPackError(f"{path} must contain packs table or list")
