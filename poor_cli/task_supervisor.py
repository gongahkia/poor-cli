"""Detached task supervisor entry point."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from .task_manager import TaskManager, run_task_worker


def _event(event: str, **details: Any) -> str:
    return json.dumps(
        {
            "event": event,
            "ts": datetime.now(timezone.utc).isoformat(),
            "pid": os.getpid(),
            **details,
        },
        ensure_ascii=False,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m poor_cli.task_supervisor")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--config")
    args = parser.parse_args(list(argv) if argv is not None else None)

    repo_root = Path(args.repo_root).expanduser().resolve()
    manager = TaskManager(repo_root)
    task = manager.get_task(args.task_id)
    if task is None:
        print(_event("supervisor_error", taskId=args.task_id, error="unknown task"), flush=True)
        return 1

    print(_event("supervisor_started", taskId=task.task_id), flush=True)
    try:
        code = asyncio.run(
            run_task_worker(
                repo_root=repo_root,
                task_id=task.task_id,
                config_path=Path(args.config).expanduser() if args.config else None,
            )
        )
    except BaseException as exc:
        print(_event("supervisor_error", taskId=task.task_id, error=str(exc)), flush=True)
        raise
    print(_event("supervisor_finished", taskId=task.task_id, exitCode=code), flush=True)
    return int(code)


if __name__ == "__main__":
    raise SystemExit(main())
