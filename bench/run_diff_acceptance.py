#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from poor_cli.run_records import diff_runs, fork_run
from poor_cli.store import RunStore


def acceptance_payload() -> dict[str, Any]:
    with TemporaryDirectory(prefix="poor-cli-run-diff-") as temp:
        root = Path(temp)
        store = RunStore(root / "store")
        try:
            run_a = store.create_run(user_goal="a", repo_path=root, git_commit_start="abc", mode="balanced", budget={})
            run_b = store.create_run(user_goal="b", repo_path=root, git_commit_start="abc", mode="balanced", budget={})
            store.append_event(run_a, "route.selected", {"profile": "openai"})
            store.append_event(run_b, "route.selected", {"profile": "local"})
            store.put_artifact(run_id=run_a, kind="artifact.worker.patch", data="diff a\n", media_type="text/x-diff")
            store.put_artifact(run_id=run_b, kind="artifact.worker.patch", data="diff b\n", media_type="text/x-diff")
            diff = diff_runs(store, run_a, run_b)
            fork = fork_run(store, run_a)
            fork_row = store.get_run(str(fork["fork_run_id"]))
        finally:
            store.close()
    sections = {change["section"] for change in diff["changes"]}
    checks = {
        "route_change": "route" in sections,
        "artifact_change": "artifacts" in sections,
        "repo_delta_change": "repo_delta" in sections,
        "fail_on_change": bool(diff["changed"]),
        "fork_record": fork_row["status"] == "forked" and fork["source_run_id"] == run_a,
    }
    return {
        "schema_version": "poor-cli-run-diff-acceptance-v1",
        "accepted": all(checks.values()),
        "checks": checks,
        "diff_schema_version": diff["schema_version"],
        "fork_schema_version": fork["schema_version"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(prog="bench/run_diff_acceptance.py")
    parser.add_argument("--output")
    args = parser.parse_args()
    payload = acceptance_payload()
    body = json.dumps(payload, indent=2, sort_keys=True)
    print(body)
    if args.output:
        Path(args.output).write_text(body + "\n", encoding="utf-8")
    return 0 if payload["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
