"""State and session CLI subcommands: checkpoint, history, session, memory."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, indent=2, default=str))


def run_checkpoint_mode(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="poor-cli checkpoint")
    sub = parser.add_subparsers(dest="subcommand", required=True)
    p_list = sub.add_parser("list")
    p_list.add_argument("--limit", type=int)
    p_list.add_argument("--json", action="store_true")
    p_create = sub.add_parser("create")
    p_create.add_argument("--description", "-d", default="manual checkpoint")
    p_create.add_argument("files", nargs="*")
    p_create.add_argument("--json", action="store_true")
    p_preview = sub.add_parser("preview")
    p_preview.add_argument("checkpoint_id")
    p_preview.add_argument("--json", action="store_true")
    p_restore = sub.add_parser("restore")
    p_restore.add_argument("checkpoint_id")
    p_restore.add_argument("--json", action="store_true")
    args = parser.parse_args(list(argv))
    from ..checkpoint import CheckpointManager
    mgr = CheckpointManager(workspace_root=Path.cwd())
    if args.subcommand == "list":
        checkpoints = mgr.list_checkpoints(limit=args.limit)
        payload = [c.to_dict() for c in checkpoints]
        if args.json:
            _print_json(payload)
        else:
            if not payload:
                print("No checkpoints found.")
            for c in payload:
                print(f"  {c['checkpoint_id']}  {c['created_at']}  {c['description']}  ({c['file_count']} files)")
        return 0
    if args.subcommand == "create":
        cp = mgr.create_checkpoint(file_paths=args.files or [], description=args.description)
        payload = cp.to_dict()
        if args.json:
            _print_json(payload)
        else:
            print(f"Checkpoint {payload['checkpoint_id']} created ({payload['file_count']} files)")
        return 0
    if args.subcommand == "preview":
        diffs = mgr.preview_checkpoint(args.checkpoint_id)
        if args.json:
            _print_json(diffs)
        else:
            if not diffs:
                print("No file changes in checkpoint.")
            for d in diffs:
                print(f"  {d.get('status', '?'):10s} {d.get('filePath', '?')}")
        return 0
    if args.subcommand == "restore":
        count = mgr.restore_checkpoint(args.checkpoint_id)
        payload = {"checkpoint_id": args.checkpoint_id, "restored_files": count}
        if args.json:
            _print_json(payload)
        else:
            print(f"Restored {count} files from checkpoint {args.checkpoint_id}")
        return 0
    raise SystemExit(f"Unknown checkpoint subcommand: {args.subcommand}")


def run_history_mode(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="poor-cli history")
    sub = parser.add_subparsers(dest="subcommand", required=True)
    p_list = sub.add_parser("list")
    p_list.add_argument("--limit", type=int, default=10)
    p_list.add_argument("--json", action="store_true")
    p_search = sub.add_parser("search")
    p_search.add_argument("query")
    p_search.add_argument("--limit", type=int, default=20)
    p_search.add_argument("--json", action="store_true")
    p_export = sub.add_parser("export")
    p_export.add_argument("session_id")
    p_export.add_argument("--output", "-o", required=True)
    args = parser.parse_args(list(argv))
    from ..history import HistoryManager
    mgr = HistoryManager()
    if args.subcommand == "list":
        sessions = mgr.list_sessions(limit=args.limit)
        if args.json:
            _print_json([{"session_id": s[0], "started_at": s[1], "message_count": s[2]} for s in sessions])
        else:
            if not sessions:
                print("No sessions found.")
            for sid, started, count in sessions:
                print(f"  {sid}  {started}  ({count} messages)")
        return 0
    if args.subcommand == "search":
        results = mgr.search_messages(args.query, limit=args.limit)
        if args.json:
            _print_json(results)
        else:
            if not results:
                print("No results found.")
            for r in results:
                print(f"  [{r.get('role', '?')}] {r.get('content', '')[:120]}")
        return 0
    if args.subcommand == "export":
        mgr.export_session(args.session_id, Path(args.output).expanduser())
        print(f"Exported session {args.session_id} to {args.output}")
        return 0
    raise SystemExit(f"Unknown history subcommand: {args.subcommand}")


def run_session_mode(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="poor-cli session")
    sub = parser.add_subparsers(dest="subcommand", required=True)
    p_list = sub.add_parser("list")
    p_list.add_argument("--limit", type=int, default=10)
    p_list.add_argument("--json", action="store_true")
    p_create = sub.add_parser("create")
    p_create.add_argument("--label", default="")
    p_create.add_argument("--json", action="store_true")
    p_fork = sub.add_parser("fork")
    p_fork.add_argument("source_id")
    p_fork.add_argument("--label", default="")
    p_fork.add_argument("--json", action="store_true")
    p_destroy = sub.add_parser("destroy")
    p_destroy.add_argument("session_id")
    p_destroy.add_argument("--json", action="store_true")
    args = parser.parse_args(list(argv))
    from ..session_manager import SessionManager
    mgr = SessionManager()
    if args.subcommand == "list":
        sessions = mgr.list_sessions()
        if args.json:
            _print_json(sessions)
        else:
            if not sessions:
                print("No sessions found.")
            for s in sessions:
                sid = s.get("session_id", s.get("id", "?"))
                label = s.get("label", "")
                status = s.get("status", "")
                print(f"  {sid}  {label}  {status}")
        return 0
    if args.subcommand == "create":
        session = mgr.create_session(label=args.label)
        payload = {"session_id": session.session_id, "label": args.label}
        if args.json:
            _print_json(payload)
        else:
            print(f"Session {session.session_id} created")
        return 0
    if args.subcommand == "fork":
        session = mgr.fork_session(args.source_id, label=args.label)
        payload = {"session_id": session.session_id, "forked_from": args.source_id}
        if args.json:
            _print_json(payload)
        else:
            print(f"Session {session.session_id} forked from {args.source_id}")
        return 0
    if args.subcommand == "destroy":
        mgr.destroy_session(args.session_id)
        if args.json:
            _print_json({"destroyed": args.session_id})
        else:
            print(f"Session {args.session_id} destroyed")
        return 0
    raise SystemExit(f"Unknown session subcommand: {args.subcommand}")


def run_state_mode(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="poor-cli state")
    sub = parser.add_subparsers(dest="subcommand", required=True)
    p_export = sub.add_parser("export")
    p_export.add_argument("--output", "-o", required=True)
    p_export.add_argument("--json", action="store_true")
    p_import = sub.add_parser("import")
    p_import.add_argument("archive")
    p_import.add_argument("--replace", action="store_true", help="overwrite existing local state files")
    p_import.add_argument("--json", action="store_true")
    args = parser.parse_args(list(argv))
    from ..state_portability import export_state, import_state
    if args.subcommand == "export":
        result = export_state(Path(args.output), repo_root=Path.cwd())
        payload = result.to_dict()
        if args.json:
            _print_json(payload)
        else:
            print(f"Exported {len(result.files)} state files to {result.archive}")
        return 0
    if args.subcommand == "import":
        result = import_state(Path(args.archive), repo_root=Path.cwd(), replace=args.replace)
        payload = result.to_dict()
        if args.json:
            _print_json(payload)
        else:
            print(f"Imported {len(result.files)} state files from {result.archive}")
            if result.skipped:
                print(f"Skipped {len(result.skipped)} existing/unknown files")
        return 0
    raise SystemExit(f"Unknown state subcommand: {args.subcommand}")


def run_memory_mode(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="poor-cli memory")
    sub = parser.add_subparsers(dest="subcommand", required=True)
    p_list = sub.add_parser("list")
    p_list.add_argument("--type")
    p_list.add_argument("--json", action="store_true")
    p_save = sub.add_parser("save")
    p_save.add_argument("--name", required=True)
    p_save.add_argument("--type", default="project")
    p_save.add_argument("--description", default="")
    p_save.add_argument("--content", required=True)
    p_save.add_argument("--json", action="store_true")
    p_search = sub.add_parser("search")
    p_search.add_argument("query")
    p_search.add_argument("--limit", type=int, default=10)
    p_search.add_argument("--lod", action="store_true", help="return mixed full/summary/headline results")
    p_search.add_argument("--alpha", type=float, default=0.65, help="LOD semantic-vs-recency weight")
    p_search.add_argument("--profile", choices=("semantic", "balanced", "recency"), default="")
    p_search.add_argument("--query-mode", choices=("auto", "recent", "last_week", "never_seen", "ignored"), default="auto")
    p_search.add_argument("--exclude", action="append", default=[])
    p_search.add_argument("--json", action="store_true")
    p_expand = sub.add_parser("expand")
    p_expand.add_argument("name")
    p_expand.add_argument("--json", action="store_true")
    p_promote = sub.add_parser("promote")
    p_promote.add_argument("name")
    p_promote.add_argument("--json", action="store_true")
    p_delete = sub.add_parser("delete")
    p_delete.add_argument("name")
    p_delete.add_argument("--json", action="store_true")
    p_review = sub.add_parser("review")
    p_review.add_argument("--accept-all", action="store_true", help="bulk accept every pending memory")
    p_review.add_argument("--reject-all", action="store_true", help="bulk reject every pending memory")
    p_review.add_argument("--json", action="store_true")
    p_expire = sub.add_parser("expire", help="list or archive expired memories (MH3)")
    p_expire.add_argument("--archive", action="store_true", help="actually archive (default lists only)")
    p_expire.add_argument("--dry-run", action="store_true", help="show what archive would do without writing")
    p_expire.add_argument("--json", action="store_true")
    args = parser.parse_args(list(argv))
    from ..memory import MemoryManager, MemoryEntry
    mgr = MemoryManager(repo_root=Path.cwd(), prefer_agent_rules=True)
    mgr.load()
    if args.subcommand == "list":
        entries = mgr.list_all(type_filter=args.type)
        payload = [e.to_dict() for e in entries]
        if args.json:
            _print_json(payload)
        else:
            if not payload:
                print("No memory entries found.")
            for e in payload:
                print(f"  [{e.get('type', '?')}] {e.get('name', '?')}: {e.get('description', '')}")
        return 0
    if args.subcommand == "save":
        entry = MemoryEntry(name=args.name, type=args.type, description=args.description, content=args.content)
        mgr.save(entry)
        if args.json:
            _print_json(entry.to_dict())
        else:
            print(f"Saved memory entry: {args.name}")
        return 0
    if args.subcommand == "search":
        if args.lod:
            import asyncio
            from ..memory_lod import render_lod_results, search_lod
            results = asyncio.run(search_lod(
                mgr,
                args.query,
                max_results=args.limit,
                alpha=args.alpha,
                alpha_profile=args.profile,
                query_mode=args.query_mode,
                exclude=args.exclude,
            ))
            payload = [e.to_dict() for e in results]
            if args.json:
                _print_json(payload)
            else:
                print(render_lod_results(results))
            return 0
        results = mgr.search(args.query, max_results=args.limit)
        payload = [e.to_dict() for e in results]
        if args.json:
            _print_json(payload)
        else:
            if not payload:
                print("No results found.")
            for e in payload:
                print(f"  [{e.get('type', '?')}] {e.get('name', '?')}: {e.get('description', '')}")
        return 0
    if args.subcommand == "expand":
        from ..memory_lod import expand_memory
        entry = expand_memory(mgr, args.name)
        if entry is None:
            raise SystemExit(f"Memory entry not found: {args.name}")
        if args.json:
            _print_json(entry.to_dict())
        else:
            print(f"# {entry.name}\n\n{entry.content}")
        return 0
    if args.subcommand == "promote":
        from ..memory_lod import promote_memory
        entry = promote_memory(mgr, args.name)
        if entry is None:
            raise SystemExit(f"Memory entry not found: {args.name}")
        if args.json:
            _print_json(entry.to_dict())
        else:
            print(f"Promoted memory entry: {entry.name}")
        return 0
    if args.subcommand == "delete":
        deleted = mgr.delete(args.name)
        if not deleted:
            raise SystemExit(f"Memory entry not found: {args.name}")
        if args.json:
            _print_json({"deleted": args.name})
        else:
            print(f"Deleted memory entry: {args.name}")
        return 0
    if args.subcommand == "review":
        from ..memory_review import bulk_accept, bulk_reject, list_pending
        pending = list_pending(mgr)
        if args.accept_all:
            summary = bulk_accept(mgr)
            payload = summary.to_dict()
            if args.json:
                _print_json(payload)
            else:
                print(f"Accepted {len(payload['accepted'])} memories.")
            return 0
        if args.reject_all:
            summary = bulk_reject(mgr)
            payload = summary.to_dict()
            if args.json:
                _print_json(payload)
            else:
                print(f"Rejected {len(payload['rejected'])} memories.")
            return 0
        payload = [e.to_dict() for e in pending]
        if args.json:
            _print_json(payload)
        else:
            if not payload:
                print("No pending memories to review.")
            for e in payload:
                print(f"  [{e.get('type', '?')}] {e.get('name', '?')}: {e.get('description', '')}")
                print(f"     filename: {e.get('filename', '')}")
                src = e.get("sourceSessionId", "")
                if src:
                    print(f"     source:   {src} ({e.get('extractor', '?')})")
                print()
            if payload:
                print("Use --accept-all or --reject-all to act on the entire pile.")
                print("Per-entry edits are handled by `poor-cli memory review`.")
        return 0
    if args.subcommand == "expire":
        from ..memory_forgetting import MemoryForgetter
        forgetter = MemoryForgetter(mgr)
        if args.archive:
            summary = forgetter.run_expiry_pass(dry_run=args.dry_run)
            payload = summary.to_dict()
            if args.json:
                _print_json(payload)
            else:
                action = "would archive" if args.dry_run else "archived"
                print(f"{action} {len(payload['archived'])} memories.")
                for name in payload["archived"]:
                    print(f"  - {name}")
            return 0
        # default: just list candidates (no mutation)
        stale = forgetter.due_for_expiry()
        payload = [e.to_dict() for e in stale]
        if args.json:
            _print_json(payload)
        else:
            if not stale:
                print("No memories due for expiry.")
                print("(feedback never expires; user 365d; project 180d; reference 90d.)")
            for e in payload:
                last = e.get("lastAccessedAt") or e.get("updatedAt") or "?"
                print(f"  [{e.get('type', '?')}] {e.get('name', '?')} — last accessed {last}, hits {e.get('hitCount', 0)}")
            if stale:
                print()
                print("Run with --archive to move expired entries to <memory_dir>/archive/.")
                print("Add --dry-run to preview the archive call without writing.")
        return 0
    raise SystemExit(f"Unknown memory subcommand: {args.subcommand}")
