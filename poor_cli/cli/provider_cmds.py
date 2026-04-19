"""Provider CLI subcommands."""

from __future__ import annotations

import argparse
import json
from typing import Any, Sequence


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, indent=2, default=str))


def _core_cls():
    from ..core import PoorCLICore
    return PoorCLICore


def _provider_info_fast(config_path_hint: str | None = None) -> dict[str, Any]:
    from ..config_fast import load_runtime_model_settings

    settings = load_runtime_model_settings(config_path_hint)
    return {
        "name": str(settings.get("provider", "openai")),
        "model": str(settings.get("model", "")),
        "routingMode": str(settings.get("routingMode", "manual")),
        "initialized": False,
        "capabilities": {},
        "supported_clients": ["cli", "neovim"],
    }


def run_provider_mode(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="poor-cli provider")
    sub = parser.add_subparsers(dest="subcommand", required=True)
    p_list = sub.add_parser("list")
    p_list.add_argument("--json", action="store_true")
    p_info = sub.add_parser("info")
    p_info.add_argument("--config", help="config file path")
    p_info.add_argument("--json", action="store_true")
    p_switch = sub.add_parser("switch")
    p_switch.add_argument("name")
    p_switch.add_argument("model", nargs="?")
    p_switch.add_argument("--config", help="config file path")
    p_switch.add_argument("--json", action="store_true")
    args = parser.parse_args(list(argv))
    if args.subcommand == "list":
        from ..providers.provider_factory import ProviderFactory

        payload = [{"name": name} for name in ProviderFactory.list_provider_names(include_aliases=True)]
        if args.json:
            _print_json(payload)
        else:
            for provider in payload:
                print(f"  {provider['name']}")
        return 0
    if args.subcommand == "info":
        info = _provider_info_fast(args.config)
        if args.json:
            _print_json(info)
        else:
            for key, value in info.items():
                print(f"  {key}: {value}")
        return 0
    if args.subcommand == "switch":
        import asyncio
        from pathlib import Path

        async def _switch() -> dict[str, Any]:
            core = _core_cls()(config_path=Path(args.config).expanduser() if args.config else None)
            await core.initialize()
            try:
                await core.switch_provider(args.name, model_name=args.model)
                return core.get_provider_info()
            finally:
                await core.shutdown()

        info = asyncio.run(_switch())
        if args.json:
            _print_json(info)
        else:
            print(f"Switched to {info.get('name', args.name)} / {info.get('model', args.model or 'default')}")
        return 0
    raise SystemExit(f"Unknown provider subcommand: {args.subcommand}")
