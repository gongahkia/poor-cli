from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from poor_cli.replay import replay_verify
from poor_cli.store import RunStore


def main() -> int:
    with TemporaryDirectory(prefix="poor-cli-replay-gate-") as temp:
        root = Path(temp)
        store = RunStore(root / "store")
        run_id = store.create_run(user_goal="determinism", repo_path=root, git_commit_start="abc", mode="balanced", budget={})
        store.append_event(run_id, "gate.event", {"ok": True})
        store.put_artifact(run_id=run_id, kind="gate.artifact", data={"ok": True})
        first = replay_verify(store, run_id)
        second = replay_verify(store, run_id)
        store.close()
    accepted = first == second and bool(first.get("verified"))
    print(json.dumps({"accepted": accepted, "first": first, "second": second}, indent=2, sort_keys=True))
    return 0 if accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())
