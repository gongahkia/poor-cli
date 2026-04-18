import asyncio
import tempfile
import time
import unittest
from pathlib import Path

from poor_cli.config import Config
from poor_cli.core import PoorCLICore
from poor_cli.providers.base import FunctionCall, ProviderResponse
from poor_cli.run_history import RunHistoryManager


class _ProviderStub:
    @staticmethod
    def format_tool_results(payload):
        return payload


class RunDiagnosticsTests(unittest.TestCase):
    def test_list_runs_projects_diagnostics(self):
        core = PoorCLICore()
        core.config = Config()

        with tempfile.TemporaryDirectory() as tmpdir:
            manager = RunHistoryManager(Path(tmpdir))
            core._run_history = manager
            run = manager.start_run(
                source_kind="session",
                source_id="diag-session",
                metadata={
                    "completionReasonCode": "complete",
                    "turnTransitions": [{"reasonCode": "run_started", "iterationIndex": 0}],
                    "turnOrchestration": [{"iterationIndex": 0, "callCount": 2}],
                    "perfSpans": [{"name": "core.initialize.total", "elapsedMs": 12.3}],
                },
            )
            manager.finish_run(run.run_id, status="completed", summary="ok")

            payload = core.list_runs(limit=1)
            self.assertEqual(len(payload), 1)
            self.assertEqual(payload[0]["completionReasonCode"], "complete")
            self.assertIn("diagnostics", payload[0])
            self.assertEqual(payload[0]["transitionCount"], 1)
            self.assertEqual(payload[0]["turnCount"], 1)
            self.assertEqual(payload[0]["diagnostics"]["turnOrchestration"][0]["callCount"], 2)
            self.assertEqual(payload[0]["diagnostics"]["perfSpans"][0]["name"], "core.initialize.total")

    def test_status_view_exposes_last_run_diagnostics(self):
        core = PoorCLICore()
        core.config = Config()

        with tempfile.TemporaryDirectory() as tmpdir:
            manager = RunHistoryManager(Path(tmpdir))
            core._run_history = manager
            run = manager.start_run(
                source_kind="session",
                source_id="diag-session",
                metadata={
                    "completionReasonCode": "cost_limit",
                    "turnTransitions": [{"reasonCode": "cost_guardrail_triggered", "iterationIndex": 1}],
                    "turnOrchestration": [{"iterationIndex": 1, "callCount": 1}],
                    "perfSpans": [{"name": "core._ensure_provider_ready", "elapsedMs": 9.1}],
                },
            )
            manager.finish_run(run.run_id, status="failed", summary="cost guardrail")

            payload = core.build_status_view()
            runs = payload["runs"]
            self.assertIn("lastRunDiagnostics", runs)
            self.assertEqual(runs["lastRunDiagnostics"]["completionReasonCode"], "cost_limit")
            self.assertEqual(runs["lastRunDiagnostics"]["turnTransitions"][0]["reasonCode"], "cost_guardrail_triggered")
            self.assertEqual(runs["lastRunDiagnostics"]["perfSpans"][0]["name"], "core._ensure_provider_ready")

    def test_record_perf_span_appends_to_active_turn_diagnostics(self):
        core = PoorCLICore()
        diagnostics = core._new_run_turn_diagnostics(max_iterations=3)
        core._active_turn_diagnostics = diagnostics

        core._record_perf_span("core._refresh_system_context", 5.432, details={"updated": True})

        spans = diagnostics["perfSpans"]
        self.assertTrue(spans)
        self.assertEqual(spans[-1]["name"], "core._refresh_system_context")
        self.assertEqual(spans[-1]["details"]["updated"], True)

    def test_new_run_turn_diagnostics_seeds_recent_perf_spans(self):
        core = PoorCLICore()
        now = time.time()
        core._perf_span_history = [
            {"at": now - 100.0, "name": "stale", "elapsedMs": 1.0},
            {"at": now - 1.0, "name": "fresh", "elapsedMs": 2.0},
        ]

        diagnostics = core._new_run_turn_diagnostics(max_iterations=2)

        self.assertEqual(len(diagnostics["perfSpans"]), 1)
        self.assertEqual(diagnostics["perfSpans"][0]["name"], "fresh")

    def test_handle_function_calls_records_turn_orchestration(self):
        async def _exercise():
            core = PoorCLICore()
            core.config = Config()
            core.provider = _ProviderStub()

            async def _allow_plan(user_request, function_calls, request_id):
                return True

            async def _exec_call(fc, iteration, max_iterations, request_id, expected_call_count=1, user_request="", **kwargs):
                result = {"id": fc.id, "name": fc.name, "result": f"ok:{fc.name}"}
                return [], result

            core._request_plan_review = _allow_plan
            core._execute_single_call_events = _exec_call
            core._is_concurrency_safe_tool = lambda name, args: name == "read_file"
            core._is_mutating_tool_call = lambda name, args: name == "write_file"
            core._should_auto_feedback = lambda: False
            core._max_tool_result_chars_per_turn = lambda: 10

            response = ProviderResponse(
                function_calls=[
                    FunctionCall(id="c1", name="read_file", arguments={"file_path": "README.md"}),
                    FunctionCall(id="c2", name="write_file", arguments={"file_path": "notes.txt", "content": "x"}),
                ]
            )
            diagnostics = core._new_run_turn_diagnostics(max_iterations=5)
            tool_results = await core._handle_function_calls_events(
                response,
                iteration=1,
                max_iterations=5,
                request_id="req-1",
                user_request="update file",
                turn_diagnostics=diagnostics,
            )

            self.assertEqual(len(diagnostics["turnOrchestration"]), 1)
            summary = diagnostics["turnOrchestration"][0]
            self.assertEqual(summary["iterationIndex"], 1)
            self.assertEqual(summary["callCount"], 2)
            self.assertEqual(summary["concurrencySafeCount"], 1)
            self.assertEqual(summary["sequentialCount"], 1)
            self.assertTrue(summary["hadMutations"])
            self.assertTrue(summary["toolResultBudgetApplied"])
            self.assertGreater(summary["truncatedResultCount"], 0)
            self.assertEqual(len(tool_results), 2)
            self.assertIn("tool-result", tool_results[1]["result"])

        asyncio.run(_exercise())


if __name__ == "__main__":
    unittest.main()
