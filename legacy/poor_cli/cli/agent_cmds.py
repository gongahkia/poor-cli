"""CLI helpers for markdown-defined agent definitions."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any, Sequence

from poor_cli.agent_definitions import AgentDefinitionRegistry


def add_definition_subcommands(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    show = subparsers.add_parser("show", help="Show a markdown-defined subagent")
    show.add_argument("name")
    show.add_argument("--json", action="store_true")

    validate = subparsers.add_parser("validate", help="Validate .poor-cli/agents/*.md")
    validate.add_argument("--json", action="store_true")


def definitions_payload(repo_root: Path) -> dict[str, Any]:
    registry = AgentDefinitionRegistry(repo_root)
    return {
        "definitions": [definition.to_dict() for definition in registry.list()],
        "errors": registry.errors(),
    }


def print_definitions(repo_root: Path, *, json_output: bool = False) -> int:
    payload = definitions_payload(repo_root)
    if json_output:
        print(json.dumps(payload, indent=2))
        return 0
    definitions = payload["definitions"]
    if not definitions:
        print("No markdown agent definitions found")
    for definition in definitions:
        print(f"  {definition['name']:24s} {definition['description']}  {definition['sourcePath']}")
    if payload["errors"]:
        print("Definition errors:")
        for error in payload["errors"]:
            print(f"  {error['path']}: {error['error']}")
    return 1 if payload["errors"] else 0


def show_definition(repo_root: Path, name: str, *, json_output: bool = False) -> int:
    registry = AgentDefinitionRegistry(repo_root)
    definition = registry.get(name)
    if definition is None:
        print(f"Unknown agent definition: {name}")
        return 1
    payload = definition.to_dict()
    if json_output:
        print(json.dumps(payload, indent=2))
    else:
        print(f"{definition.name}: {definition.description}")
        print(f"source: {definition.source_path}")
        if definition.provider or definition.model:
            print(f"model: {definition.provider or '-'} / {definition.model or '-'}")
        print("allowed_tools:", ", ".join(definition.allowed_tools or ["*"]))
        print("denied_tools:", ", ".join(definition.denied_tools))
        print()
        print(definition.system_prompt)
    return 0


def validate_definitions(repo_root: Path, *, json_output: bool = False) -> int:
    return print_definitions(repo_root, json_output=json_output)


def run_definition(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="poor-cli agent run")
    parser.add_argument("name", nargs="?")
    parser.add_argument("--prompt", "-p")
    parser.add_argument("--provider")
    parser.add_argument("--model")
    parser.add_argument("--api-key")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(list(argv))
    if not args.name or not args.prompt:
        parser.error("agent run requires <name> and --prompt")
    return asyncio.run(_run_definition_async(args))


async def _run_definition_async(args: argparse.Namespace) -> int:
    from poor_cli.core import PoorCLICore
    from poor_cli.sub_agent import SubAgent

    core = PoorCLICore()
    await core.initialize(provider_name=args.provider, model_name=args.model, api_key=args.api_key)
    try:
        registry = AgentDefinitionRegistry(Path.cwd(), available_tools=core.tool_registry.tools.keys())
        definition = registry.get(args.name)
        if definition is None:
            payload = {"error": f"unknown agent definition: {args.name}", "errors": registry.errors()}
            if args.json:
                print(json.dumps(payload, indent=2))
            else:
                print(payload["error"])
            return 1
        agent = SubAgent(core, agent_definition=definition)
        result = await agent.run(str(args.prompt))
        if args.json:
            print(json.dumps({"agent": definition.name, "result": result, "usage": agent.get_usage()}, indent=2))
        else:
            print(result)
        return 0
    finally:
        await core.shutdown()
