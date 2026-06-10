import tempfile
import unittest
from pathlib import Path

from poor_cli.agent_runner import AgentManager
from poor_cli.lifecycle_events import build_lifecycle_event
from poor_cli.task_manager import TaskManager


class LifecycleSemanticsTests(unittest.TestCase):
    def test_build_lifecycle_event_shape(self):
        payload = build_lifecycle_event(
            stream="task",
            entity_id="task-123",
            stage="finished",
            status="failed",
            reason_code="tool_failure",
            run_id="run-1",
            details={"error": "boom"},
        )
        self.assertEqual(payload["type"], "lifecycle")
        data = payload["data"]
        self.assertEqual(data["stream"], "task")
        self.assertEqual(data["entityId"], "task-123")
        self.assertEqual(data["stage"], "finished")
        self.assertEqual(data["status"], "failed")
        self.assertEqual(data["reasonCode"], "tool_failure")
        self.assertEqual(data["runId"], "run-1")
        self.assertIn("at", data)
        self.assertEqual(data["details"]["error"], "boom")

    def test_task_terminal_metadata_and_resume_metadata(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = TaskManager(Path(tmpdir))
            task = manager.create_task(
                title="Test",
                prompt="Do thing",
                sandbox_preset="read-only",
                source="manual",
                auto_start=False,
            )
            run = manager.run_history.start_run(
                source_kind="task",
                source_id=task.task_id,
                metadata={
                    "completionReasonCode": "cost_limit",
                    "turnTransitions": [{"reasonCode": "cost_guardrail_triggered"}],
                    "turnOrchestration": [{"iterationIndex": 1}],
                },
            )
            manager.run_history.finish_run(run.run_id, status="failed", summary="guardrail")

            task = manager.attach_run(task.task_id, run.run_id)
            self.assertEqual(task.metadata.get("lastRunId"), run.run_id)
            self.assertEqual(task.metadata.get("lastRunCompletionReasonCode"), "cost_limit")
            self.assertEqual(task.metadata.get("lastRunTransitionCount"), 1)
            self.assertEqual(task.metadata.get("lastRunTurnCount"), 1)
            self.assertEqual(task.metadata.get("resume", {}).get("runId"), run.run_id)

            failed = manager.mark_failed(task.task_id, error_message="permission denied")
            self.assertEqual(failed.metadata.get("lastTerminalStatus"), "failed")
            self.assertEqual(failed.metadata.get("lastTerminalReasonCode"), "policy_denial")

    def test_agent_cancel_sets_terminal_reason(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = AgentManager(Path(tmpdir))
            agent = manager.create_agent(
                prompt="Do thing",
                use_worktree=False,
                auto_start=False,
            )
            cancelled = manager.cancel_agent(agent.agent_id)
            self.assertEqual(cancelled.status, "cancelled")
            self.assertEqual(cancelled.metadata.get("lastTerminalStatus"), "cancelled")
            self.assertEqual(cancelled.metadata.get("lastTerminalReasonCode"), "cancelled_by_user")


if __name__ == "__main__":
    unittest.main()
