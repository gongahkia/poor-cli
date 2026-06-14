from __future__ import annotations

from pathlib import Path

from .replay import replay_summary
from .store import RunStore


def run_tui(store_dir: Path, run_id: str | None = None) -> None:
    from textual.app import App, ComposeResult
    from textual.containers import Horizontal, Vertical
    from textual.widgets import Footer, Header, Input, Static

    class PoorCliTui(App[None]):
        CSS = """
        #panes { height: 1fr; }
        #transcript, #activity { width: 1fr; border: solid $accent; padding: 1; }
        #composer { height: 3; }
        """

        def compose(self) -> ComposeResult:
            yield Header(show_clock=True)
            with Horizontal(id="panes"):
                yield Static(_transcript(store_dir, run_id), id="transcript")
                yield Static(_activity(store_dir), id="activity")
            with Vertical(id="composer"):
                yield Input(placeholder="poor-cli goal composer", id="goal")
            yield Footer()

    PoorCliTui().run()


def _transcript(store_dir: Path, run_id: str | None) -> str:
    if not run_id:
        return "transcript\n\nselect a run with --run-id"
    store = RunStore(store_dir)
    try:
        state = replay_summary(store, run_id)
    finally:
        store.close()
    lines = [f"transcript\n\nrun {state['run_id']} [{state['status']}] events={state['event_count']}"]
    for task_id, task in state["tasks"].items():
        lines.append(f"{task_id} {task['status']} {task['title']}")
    return "\n".join(lines)


def _activity(store_dir: Path) -> str:
    store = RunStore(store_dir)
    try:
        runs = store.list_runs()[:20]
    finally:
        store.close()
    lines = ["activity"]
    for run in runs:
        lines.append(f"{run['run_id']} {run['status']} {run['user_goal'][:60]}")
    return "\n".join(lines)
