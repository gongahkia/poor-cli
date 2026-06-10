import tempfile
import unittest
from pathlib import Path

from poor_cli.sandbox import ToolCapability, evaluate_tool_access


class SandboxCapabilityInferenceTests(unittest.TestCase):
    def _evaluate(
        self,
        *,
        tool_name: str,
        command: str = "",
        mutation_paths=None,
        permission_mode: str = "default",
        sandbox_preset: str = "workspace-write",
    ):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            original_cwd = Path.cwd()
            try:
                Path.chdir(root)  # type: ignore[attr-defined]
            except AttributeError:
                import os

                os.chdir(root)
            try:
                return evaluate_tool_access(
                    tool_name=tool_name,
                    tool_args={"command": command} if command else {},
                    tool_capabilities=[ToolCapability.PROCESS_EXECUTE.value]
                    if tool_name == "bash"
                    else [ToolCapability.NETWORK_ACCESS.value],
                    permission_mode=permission_mode,
                    sandbox_preset=sandbox_preset,
                    trusted_roots=[root],
                    mutation_paths=list(mutation_paths or []),
                )
            finally:
                import os

                os.chdir(original_cwd)

    def test_bash_curl_requires_network_access(self) -> None:
        decision = self._evaluate(tool_name="bash", command="curl https://example.com")
        self.assertFalse(decision.allowed)
        self.assertIn("network:access", decision.reason)

    def test_bash_wget_requires_network_access(self) -> None:
        decision = self._evaluate(tool_name="bash", command="wget https://example.com")
        self.assertFalse(decision.allowed)
        self.assertIn("network:access", decision.reason)

    def test_bash_gh_pr_view_requires_network_access(self) -> None:
        decision = self._evaluate(tool_name="bash", command="gh pr view 123")
        self.assertFalse(decision.allowed)
        self.assertIn("network:access", decision.reason)

    def test_bash_git_push_requires_git_write_and_network_access(self) -> None:
        decision = self._evaluate(tool_name="bash", command="git push origin main")
        self.assertFalse(decision.allowed)
        self.assertIn("network:access", decision.reason)
        self.assertIn("git:write", decision.capabilities)

    def test_bash_ls_stays_allowed_under_workspace_write(self) -> None:
        decision = self._evaluate(tool_name="bash", command="ls")
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.capabilities, [ToolCapability.PROCESS_EXECUTE.value])

    def test_fetch_url_remains_blocked_by_workspace_write(self) -> None:
        decision = self._evaluate(tool_name="fetch_url")
        self.assertFalse(decision.allowed)
        self.assertIn("network:access", decision.reason)

    def test_bash_write_inside_trusted_root_is_allowed(self) -> None:
        decision = self._evaluate(tool_name="bash", command="touch inside.txt")
        self.assertTrue(decision.allowed)
        self.assertIn("filesystem:write", decision.capabilities)

    def test_bash_write_outside_trusted_root_is_denied(self) -> None:
        decision = self._evaluate(tool_name="bash", command="touch ../outside.txt")
        self.assertFalse(decision.allowed)
        self.assertIn("trusted workspace roots", decision.reason)

    def test_plan_mode_blocks_mutating_commands(self) -> None:
        decision = self._evaluate(tool_name="bash", command="touch plan-blocked.txt", permission_mode="plan")
        self.assertFalse(decision.allowed)
        self.assertIn("plan", decision.reason)

    def test_accept_edits_prompts_for_process_execution(self) -> None:
        decision = self._evaluate(tool_name="bash", command="ls", permission_mode="acceptEdits")
        self.assertTrue(decision.allowed)
        self.assertTrue(decision.requires_approval)

    def test_bypass_permissions_allows_network_tool(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            decision = evaluate_tool_access(
                tool_name="fetch_url",
                tool_args={"url": "https://example.com"},
                tool_capabilities=[ToolCapability.NETWORK_ACCESS.value],
                permission_mode="bypassPermissions",
                sandbox_preset="workspace-write",
                trusted_roots=[root],
                mutation_paths=[],
            )
        self.assertTrue(decision.allowed)
        self.assertFalse(decision.requires_approval)


if __name__ == "__main__":
    unittest.main()
