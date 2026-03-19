import asyncio
import tempfile
import unittest
from pathlib import Path

from poor_cli.automation_manager import AutomationManager, schedule_interval
from poor_cli.config import Config
from poor_cli.context import ContextManager
from poor_cli.core import PoorCLICore
from poor_cli.run_history import RunHistoryManager
from poor_cli.task_manager import TaskManager


class ProductContractTests(unittest.TestCase):
    def test_status_view_shape_includes_canonical_sections(self) -> None:
        core = PoorCLICore()
        core.config = Config()

        payload = core.build_status_view()

        self.assertEqual(
            set(payload.keys()),
            {"session", "trust", "provider", "context", "runs", "collaboration", "recovery"},
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
            {"session", "trust", "provider", "context", "runs", "collaboration", "recovery"},
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
                provider_summary={"name": "ollama", "model": "llama3"},
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


if __name__ == "__main__":
    unittest.main()
