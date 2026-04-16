import asyncio
import json
import tempfile
import tomllib
import unittest
from pathlib import Path

from poor_cli import __version__
from poor_cli.automations import AutomationManager, parse_daily_schedule, schedule_interval
from poor_cli.config import Config
from poor_cli.context import ContextManager
from poor_cli.core import PoorCLICore
from poor_cli.policy_hooks import PolicyHookManager
from poor_cli.provider_catalog import README_MODEL_SUPPORT_HEADER, render_readme_model_support_table
from poor_cli.run_history import RunHistoryManager
from poor_cli.task_manager import TaskManager


class ProductContractTests(unittest.TestCase):
    def _readme_text(self) -> str:
        return (Path(__file__).resolve().parent.parent / "README.md").read_text(encoding="utf-8")

    def _pyproject_data(self) -> dict:
        pyproject_path = Path(__file__).resolve().parent.parent / "pyproject.toml"
        return tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

    def _readme_model_support_table(self) -> str:
        lines = self._readme_text().splitlines()
        start = lines.index(README_MODEL_SUPPORT_HEADER)
        table_lines = []
        for line in lines[start:]:
            if not line.startswith("|"):
                break
            table_lines.append(line)
        return "\n".join(table_lines)

    def test_readme_release_badge_matches_package_version(self) -> None:
        readme = self._readme_text()

        self.assertGreaterEqual(readme.count("https://img.shields.io/badge/poor-cli_"), 1)
        self.assertIn(f"poor-cli_{__version__}", readme)

    def test_readme_model_support_table_matches_provider_catalog(self) -> None:
        self.assertEqual(
            self._readme_model_support_table(),
            render_readme_model_support_table(),
        )

    def test_python_support_pinned(self) -> None:
        project = self._pyproject_data()["project"]
        readme = self._readme_text()

        self.assertEqual(project["requires-python"], ">=3.11,<3.15")
        self.assertIn(
            "Supported Python versions are `3.11`, `3.12`, `3.13`, and `3.14`.",
            readme,
        )

    def test_status_view_shape_includes_canonical_sections(self) -> None:
        core = PoorCLICore()
        core.config = Config()

        payload = core.build_status_view()

        self.assertEqual(
            set(payload.keys()),
            {"session", "trust", "provider", "context", "runs", "recovery"},
        )
        self.assertIn("routingMode", payload["session"])
        self.assertIn("sandboxPreset", payload["trust"])
        self.assertIn("audit", payload["trust"])
        self.assertIn("mcp", payload["trust"])
        self.assertIn("lastPreview", payload["context"])
        self.assertIn("recent", payload["runs"])
        self.assertIn("cost", payload["recovery"])
        self.assertIn("lastMutation", payload["recovery"])

    def test_doctor_report_shape_references_status_view(self) -> None:
        core = PoorCLICore()
        core.config = Config()

        payload = core.build_doctor_report()

        self.assertIn("summary", payload)
        self.assertIn("checks", payload)
        self.assertIn("statusView", payload)
        self.assertEqual(
            set(payload["statusView"].keys()),
            {"session", "trust", "provider", "context", "runs", "recovery"},
        )

    def test_context_preview_entries_include_explanation_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            explicit = root / "explicit.py"
            pinned = root / "pinned.py"
            explicit.write_text("print('explicit')\n", encoding="utf-8")
            pinned.write_text("print('pinned')\n", encoding="utf-8")

            manager = ContextManager(max_tokens=2000, max_files=4)
            preview = asyncio.run(
                manager.preview_context(
                    message="inspect current context selection",
                    explicit_files=[str(explicit)],
                    pinned_files=[str(pinned)],
                    repo_root=str(root),
                    max_tokens=2000,
                    max_files=1,
                )
            )

            self.assertIn("selected", preview)
            self.assertIn("excluded", preview)
            self.assertEqual(len(preview["selected"]), 1)
            self.assertGreaterEqual(len(preview["excluded"]), 1)

            for key in ("path", "reason", "tokenEstimate", "pinned", "source", "priority", "excludedReason"):
                self.assertIn(key, preview["selected"][0])
                self.assertIn(key, preview["excluded"][0])

    def test_run_record_dict_includes_required_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = RunHistoryManager(Path(tmpdir))
            run = manager.start_run(source_kind="task", source_id="abc123", metadata={"taskId": "abc123"})
            finished = manager.finish_run(
                run.run_id,
                status="completed",
                checkpoint_id="cp-1",
                provider_summary={"name": "ollama", "model": "llama3.1"},
                cost_summary={"total_tokens": 42},
                summary="completed successfully",
            )

            payload = finished.to_dict()
            self.assertEqual(
                set(payload.keys()),
                {
                    "runId",
                    "sourceKind",
                    "sourceId",
                    "status",
                    "startedAt",
                    "finishedAt",
                    "errorClass",
                    "artifactDir",
                    "checkpointId",
                    "providerSummary",
                    "costSummary",
                    "retryOfRunId",
                    "replayOfRunId",
                    "summary",
                    "metadata",
                },
            )

    def test_task_retry_and_automation_history_replay_preserve_run_links(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            task_manager = TaskManager(root)
            task = task_manager.create_task(
                title="Review docs",
                prompt="Review the docs.",
                sandbox_preset="workspace-write",
                source="manual",
                metadata={"autoApprove": True},
                auto_start=False,
                auto_approve=True,
            )

            task_run = task_manager.run_history.start_run(
                source_kind="task",
                source_id=task.task_id,
                metadata={"taskId": task.task_id},
            )
            task_manager.run_history.finish_run(task_run.run_id, status="completed", summary="ok")
            task_manager.attach_run(task.task_id, task_run.run_id)

            retry_task = task_manager.retry_task(task.task_id, auto_start=False)
            replay_task = task_manager.replay_task(task.task_id, auto_start=False)

            self.assertEqual(retry_task.metadata.get("retryOfTaskId"), task.task_id)
            self.assertEqual(retry_task.metadata.get("retryOfRunId"), task_run.run_id)
            self.assertEqual(replay_task.metadata.get("replayOfTaskId"), task.task_id)
            self.assertEqual(replay_task.metadata.get("replayOfRunId"), task_run.run_id)

            automation_manager = AutomationManager(root, task_manager=task_manager)
            automation = automation_manager.create_automation(
                name="QA sweep",
                prompt="Run QA checks.",
                schedule=schedule_interval(60),
                sandbox_preset="workspace-write",
            )

            automation_run = task_manager.run_history.start_run(
                source_kind="task",
                source_id="task-from-automation",
                metadata={
                    "automationId": automation.automation_id,
                    "automationName": automation.name,
                },
            )
            task_manager.run_history.finish_run(
                automation_run.run_id,
                status="completed",
                summary="automation run ok",
            )

            history = automation_manager.history(automation.automation_id, limit=10)
            replayed = automation_manager.replay(automation.automation_id)

            self.assertEqual(len(history), 1)
            self.assertEqual(history[0]["runId"], automation_run.run_id)
            self.assertEqual(replayed.metadata.get("replayOfRunId"), automation_run.run_id)

    def test_automation_payload_reports_timezone_and_execution_controls(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = AutomationManager(Path(tmpdir))
            automation = manager.create_automation(
                name="Morning review",
                prompt="Review the current worktree state.",
                schedule=parse_daily_schedule("09:30", timezone_name="Asia/Singapore"),
                sandbox_preset="read-only",
                metadata={
                    "execution": {
                        "executionMode": "local",
                        "reasoningEffort": "high",
                    }
                },
            )

            payload = automation.to_dict()
            self.assertEqual(payload["scheduleTimezone"], "Asia/Singapore")
            self.assertEqual(payload["executionMode"], "local")
            self.assertEqual(payload["reasoningEffort"], "high")
            self.assertIn("Asia/Singapore", payload["scheduleSummary"])

    def test_automation_cli_create_parser_accepts_timezone_and_execution_controls(self) -> None:
        from poor_cli.__main__ import _automation_schedule_from_args, _build_automation_parser

        parser = _build_automation_parser()
        args = parser.parse_args(
            [
                "create",
                "--name",
                "daily-check",
                "--prompt",
                "Run daily checks.",
                "--daily",
                "09:30",
                "--timezone",
                "Asia/Singapore",
                "--execution-mode",
                "local",
                "--reasoning-effort",
                "high",
            ]
        )

        self.assertEqual(args.timezone, "Asia/Singapore")
        self.assertEqual(args.execution_mode, "local")
        self.assertEqual(args.reasoning_effort, "high")

        schedule = _automation_schedule_from_args(args)
        self.assertEqual(schedule.get("kind"), "daily")
        self.assertEqual(schedule.get("timezone"), "Asia/Singapore")

    def test_local_execution_mode_uses_repo_root_instead_of_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            manager = TaskManager(root)
            task = manager.create_task(
                title="Inspect local checkout",
                prompt="Summarize the repo state.",
                sandbox_preset="read-only",
                source="manual",
                metadata={"execution": {"executionMode": "local"}},
                auto_start=False,
            )

            payload = task.to_dict()
            self.assertEqual(Path(task.worktree_path).resolve(), root.resolve())
            self.assertEqual(payload["executionMode"], "local")

    def test_policy_hooks_report_schema_validation_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            hooks_dir = root / ".poor-cli" / "hooks"
            hooks_dir.mkdir(parents=True, exist_ok=True)

            (hooks_dir / "valid.json").write_text(
                json.dumps(
                    {
                        "schemaVersion": 1,
                        "hooks": {
                            "task_started": [
                                {
                                    "command": "python3",
                                    "args": ["-c", "print('ok')"],
                                }
                            ]
                        },
                    }
                ),
                encoding="utf-8",
            )
            (hooks_dir / "invalid.json").write_text(
                json.dumps(
                    {
                        "schemaVersion": 1,
                        "hooks": {
                            "not_a_real_event": [
                                {
                                    "command": "python3",
                                    "args": ["-c", "print('nope')"],
                                }
                            ]
                        },
                    }
                ),
                encoding="utf-8",
            )

            manager = PolicyHookManager(root)
            status = manager.status()

            self.assertEqual(status["totalHooks"], 1)
            self.assertEqual(status["supportedSchemaVersions"], [1])
            self.assertIn("task_started", status["events"])
            self.assertTrue(status["validationErrors"])
            self.assertEqual(
                status["validationErrors"][0]["event"],
                "not_a_real_event",
            )


if __name__ == "__main__":
    unittest.main()
