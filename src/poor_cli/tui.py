from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .artifacts import artifact_manifest
from .config import load_config, provider_rows, save_repo_config, set_route
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
        #transcript, #activity, #provider, #graph, #artifacts { width: 1fr; border: solid $accent; padding: 1; }
        #composer { height: 3; }
        """

        def compose(self) -> ComposeResult:
            yield Header(show_clock=True)
            with Horizontal(id="panes"):
                with Vertical():
                    yield Static(render_provider_panel(store_dir, Path.cwd()), id="provider")
                    yield Static(render_run_graph_panel(store_dir, self.selected_run_id), id="graph")
                with Vertical():
                    yield Static(_transcript(store_dir, self.selected_run_id), id="transcript")
                    yield Static(render_artifact_panel(store_dir, self.selected_run_id), id="artifacts")
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
                self.query_one("#graph", Static).update(render_run_graph_panel(store_dir, self.selected_run_id))
                self.query_one("#artifacts", Static).update(render_artifact_panel(store_dir, self.selected_run_id))
                self.query_one("#provider", Static).update(render_provider_panel(store_dir, Path.cwd()))
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
    if text.startswith("route set "):
        return _handle_route_set(text.split()[2:], repo_path or Path.cwd())
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


def render_provider_panel(store_dir: Path, repo_path: Path | None = None) -> str:
    del store_dir
    config = load_config(repo_path or Path.cwd())
    lines = ["provider"]
    for row in provider_rows(config):
        marker = "*" if row["active"] else " "
        lines.append(
            f"{marker} {row['id']} {row['kind']} model={row['model'] or '-'} host={row['base_url'] or '-'} "
            f"tools={row['tools']} web={row['web']}"
        )
    route = config.get("routes", {}).get("executor") if isinstance(config.get("routes"), dict) else {}
    if isinstance(route, dict):
        lines.append(f"route executor profile={route.get('profile') or '-'} model={route.get('model') or '-'}")
    budget = config.get("budgets") if isinstance(config.get("budgets"), dict) else {}
    lines.append(f"budget max_usd={budget.get('max_usd', '-')}")
    return "\n".join(lines)


def render_run_graph_panel(store_dir: Path, run_id: str | None) -> str:
    if not run_id:
        return "run graph\n\nno run selected"
    store = RunStore(store_dir)
    try:
        tasks = store.list_tasks(run_id)
        events = store.list_events(run_id)
    finally:
        store.close()
    review = "seen" if any(event["type"].startswith("review.") for event in events) else "pending"
    verify = "seen" if any(event["type"].startswith("verify.") for event in events) else "pending"
    lines = [f"run graph\n\nrun {run_id} review={review} verifier={verify}"]
    for task in tasks:
        deps = ", ".join(task.get("dependencies") or []) or "-"
        lines.append(f"{task['task_id']} {task['status']} deps={deps} {task['title']}")
    failures = [event for event in events if "failed" in event["type"] or "blocked" in event["type"]]
    if failures:
        lines.append(f"failures={len(failures)}")
    return "\n".join(lines)


def render_artifact_panel(store_dir: Path, run_id: str | None, artifact_id: str | None = None) -> str:
    if not run_id:
        return "artifacts\n\nno run selected"
    store = RunStore(store_dir)
    try:
        if artifact_id:
            return store.artifact_payload(artifact_id).decode("utf-8", errors="replace")
        rows = artifact_manifest(store, run_id)
    finally:
        store.close()
    lines = ["artifacts"]
    for row in rows[:30]:
        lines.append(f"{row['path']} {row['size']}b")
    return "\n".join(lines)


def _handle_route_set(parts: list[str], repo_path: Path) -> TuiCommandResult:
    values: dict[str, str] = {}
    iterator = iter(parts)
    for part in iterator:
        if part in {"--role", "--profile", "--model"}:
            values[part[2:]] = next(iterator, "")
    role = values.get("role")
    profile = values.get("profile")
    if not role or not profile:
        raise RuntimeError("route set requires --role and --profile")
    path = save_repo_config(set_route(load_config(repo_path, include_env=False), role, profile, values.get("model")), repo_path)
    return TuiCommandResult(None, f"route {role} profile={profile} wrote {path}")


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
