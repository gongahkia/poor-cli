from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .models import Budget
from .orchestrator import Orchestrator
from .replay import replay_summary
from .store import RunStore


@dataclass(frozen=True)
class TuiCommandResult:
    run_id: str | None
    message: str


def run_tui(store_dir: Path, run_id: str | None = None) -> None:
    from textual.app import App, ComposeResult
    from textual.containers import Horizontal, Vertical
    from textual.widgets import Footer, Header, Input, Static

    class PoorCliTui(App[None]):
        def __init__(self) -> None:
            super().__init__()
            self.selected_run_id = run_id

        CSS = """
        #panes { height: 1fr; }
        #transcript, #activity { width: 1fr; border: solid $accent; padding: 1; }
        #composer { height: 3; }
        """

        def compose(self) -> ComposeResult:
            yield Header(show_clock=True)
            with Horizontal(id="panes"):
                yield Static(_transcript(store_dir, self.selected_run_id), id="transcript")
                yield Static(_activity(store_dir), id="activity")
            with Vertical(id="composer"):
                yield Input(placeholder="run --dry <goal> | run --yes <goal> | replay <run_id>", id="goal")
            yield Footer()

        def on_input_submitted(self, event: Input.Submitted) -> None:
            command = event.value.strip()
            event.input.value = ""
            try:
                result = handle_tui_command(store_dir, command, repo_path=Path.cwd())
                self.selected_run_id = result.run_id or self.selected_run_id
                self.query_one("#transcript", Static).update(_transcript(store_dir, self.selected_run_id))
                self.query_one("#activity", Static).update(_activity(store_dir))
            except Exception as exc:
                self.query_one("#transcript", Static).update(f"error\n\n{exc}")

    PoorCliTui().run()


def handle_tui_command(store_dir: Path, command: str, *, repo_path: Path | None = None) -> TuiCommandResult:
    text = command.strip()
    if not text:
        return TuiCommandResult(None, "empty command")
    if text.startswith("replay "):
        run_id = text.split(maxsplit=1)[1].strip()
        return TuiCommandResult(run_id, _transcript(store_dir, run_id))
    if text.startswith("run "):
        return _handle_run(store_dir, text.split(maxsplit=1)[1].strip(), repo_path or Path.cwd())
    return _handle_run(store_dir, text, repo_path or Path.cwd())


def _handle_run(store_dir: Path, command: str, repo_path: Path) -> TuiCommandResult:
    dry_run = True
    goal = command
    if command.startswith("--yes "):
        dry_run = False
        goal = command.split(maxsplit=1)[1].strip()
    elif command.startswith("--dry "):
        goal = command.split(maxsplit=1)[1].strip()
    if not goal:
        raise RuntimeError("run goal is required")
    budget = Budget()
    store = RunStore(store_dir)
    try:
        orchestrator = Orchestrator(store, repo_path)
        run_id, _plan = orchestrator.plan(goal, budget)
        exit_code = orchestrator.run(run_id, budget, dry_run=dry_run)
        return TuiCommandResult(run_id, f"run {run_id} exit={exit_code}")
    finally:
        store.close()


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
