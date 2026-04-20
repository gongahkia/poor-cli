from __future__ import annotations

import argparse
from pathlib import Path

from seuss.commands.approve_cmd import (
    run_approve_accept,
    run_approve_accept_all,
    run_approve_list,
    run_approve_reject,
)
from seuss.commands.eval_cmd import run_eval
from seuss.commands.generate_cmd import run_generate
from seuss.commands.ingest_cmd import run_ingest
from seuss.commands.init_cmd import run_init
from seuss.commands.inspect_cmd import run_inspect
from seuss.commands.memory_cmd import (
    run_memory_add,
    run_memory_delete,
    run_memory_import,
    run_memory_list,
)
from seuss.config import DEFAULT_CONFIG_PATH, ConfigError


def _add_config_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to seuss YAML config.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="seuss", description="Seuss Phase 1 CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    init_parser = sub.add_parser("init", help="Initialize config and workspace")
    init_parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    init_parser.add_argument("--force", action="store_true")

    ingest_parser = sub.add_parser("ingest", help="Ingest configured sources")
    _add_config_arg(ingest_parser)
    ingest_parser.add_argument("--source", default=None)
    ingest_parser.add_argument("--dry-run", action="store_true")
    ingest_parser.add_argument("--rebuild", action="store_true")

    inspect_parser = sub.add_parser("inspect", help="Inspect corpus and memory")
    _add_config_arg(inspect_parser)
    inspect_parser.add_argument("mode", nargs="?", choices=["corpus", "source", "phrases"], default=None)
    inspect_parser.add_argument("--source", default=None)
    inspect_parser.add_argument("--limit", type=int, default=25)

    generate_parser = sub.add_parser("generate", help="Generate text")
    _add_config_arg(generate_parser)
    generate_parser.add_argument("--prompt", default="")
    generate_parser.add_argument(
        "--level",
        choices=["character", "word", "phrase", "hybrid"],
        default=None,
    )
    generate_parser.add_argument("--max-tokens", type=int, default=None)
    generate_parser.add_argument("--temperature", type=float, default=None)
    generate_parser.add_argument("--seed", type=int, default=None)
    generate_parser.add_argument("--save", action="store_true")

    memory_parser = sub.add_parser("memory", help="Manage memory")
    mem_sub = memory_parser.add_subparsers(dest="memory_command", required=True)

    memory_list_parser = mem_sub.add_parser("list", help="List memory records")
    _add_config_arg(memory_list_parser)

    memory_add_parser = mem_sub.add_parser("add", help="Add memory record")
    _add_config_arg(memory_add_parser)
    memory_add_parser.add_argument("text")
    memory_add_parser.add_argument("--kind", default="style")

    memory_import_parser = mem_sub.add_parser("import", help="Import memory from JSONL")
    _add_config_arg(memory_import_parser)
    memory_import_parser.add_argument("path")
    memory_import_parser.add_argument("--text-field", default="text")

    memory_delete_parser = mem_sub.add_parser("delete", help="Delete memory by id")
    _add_config_arg(memory_delete_parser)
    memory_delete_parser.add_argument("id")

    approve_parser = sub.add_parser("approve", help="Approve or reject training examples")
    approve_sub = approve_parser.add_subparsers(dest="approve_command", required=True)

    approve_list_parser = approve_sub.add_parser("list", help="List queue examples")
    _add_config_arg(approve_list_parser)
    approve_list_parser.add_argument("--all", action="store_true")

    approve_accept_parser = approve_sub.add_parser("accept", help="Approve one example")
    _add_config_arg(approve_accept_parser)
    approve_accept_parser.add_argument("id")

    approve_reject_parser = approve_sub.add_parser("reject", help="Reject one example")
    _add_config_arg(approve_reject_parser)
    approve_reject_parser.add_argument("id")

    approve_accept_all_parser = approve_sub.add_parser("accept-all", help="Approve all pending")
    _add_config_arg(approve_accept_all_parser)
    approve_accept_all_parser.add_argument("--source", default=None)

    eval_parser = sub.add_parser("eval", help="Run evaluation suite")
    _add_config_arg(eval_parser)
    eval_parser.add_argument("--suite", default="phase1")
    eval_parser.add_argument("--seed", type=int, default=None)
    eval_parser.add_argument("--output", default=None)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "init":
            return run_init(Path(args.config).resolve(), force=args.force)

        if args.command == "ingest":
            return run_ingest(
                config_path=Path(args.config).resolve(),
                source_name=args.source,
                dry_run=args.dry_run,
                rebuild=args.rebuild,
            )

        if args.command == "inspect":
            return run_inspect(
                config_path=Path(args.config).resolve(),
                mode=args.mode,
                source=args.source,
                limit=args.limit,
            )

        if args.command == "generate":
            return run_generate(
                config_path=Path(args.config).resolve(),
                prompt=args.prompt,
                level=args.level,
                max_tokens=args.max_tokens,
                temperature=args.temperature,
                seed=args.seed,
                save=args.save,
            )

        if args.command == "memory":
            config_path = Path(args.config).resolve()
            if args.memory_command == "list":
                return run_memory_list(config_path)
            if args.memory_command == "add":
                return run_memory_add(config_path, text=args.text, kind=args.kind)
            if args.memory_command == "import":
                return run_memory_import(
                    config_path,
                    import_path=Path(args.path).resolve(),
                    text_field=args.text_field,
                )
            if args.memory_command == "delete":
                return run_memory_delete(config_path, memory_id=args.id)

        if args.command == "approve":
            config_path = Path(args.config).resolve()
            if args.approve_command == "list":
                return run_approve_list(config_path, include_all=args.all)
            if args.approve_command == "accept":
                return run_approve_accept(config_path, record_id=args.id)
            if args.approve_command == "reject":
                return run_approve_reject(config_path, record_id=args.id)
            if args.approve_command == "accept-all":
                return run_approve_accept_all(config_path, source=args.source)

        if args.command == "eval":
            return run_eval(
                config_path=Path(args.config).resolve(),
                suite=args.suite,
                seed=args.seed,
                output_path=Path(args.output).resolve() if args.output else None,
            )

        parser.error("Unknown command")
        return 2

    except ConfigError as exc:
        print(f"Config error: {exc}")
        return 2
    except FileNotFoundError as exc:
        print(f"Missing file: {exc}")
        return 2
    except ValueError as exc:
        print(f"Invalid input: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
