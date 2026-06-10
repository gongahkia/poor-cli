import unittest
from unittest.mock import AsyncMock, MagicMock, patch, call

from poor_cli.enhanced_tools import EnhancedToolRegistry
from poor_cli.exceptions import CommandExecutionError
from poor_cli.repo_config import RepoPreferences
from poor_cli.rtk_integration import RTKState, detect_rtk, is_rtk_supported, wrap_shell_command
from poor_cli.tools_async import ToolRegistryAsync


class TestRTKDetection(unittest.TestCase):
    @patch("poor_cli.rtk_integration.shutil.which", return_value="/opt/homebrew/bin/rtk")
    def test_detect_rtk_available(self, mock_which):
        state = detect_rtk()
        self.assertTrue(state.available)
        self.assertEqual(state.binary_path, "/opt/homebrew/bin/rtk")

    @patch("poor_cli.rtk_integration._missing_warning_emitted", False)
    @patch("poor_cli.rtk_integration.logger.warning")
    @patch("poor_cli.rtk_integration.shutil.which", return_value=None)
    def test_detect_rtk_warns_when_missing_and_enabled(self, mock_which, mock_warning):
        state = detect_rtk(enabled=True)
        self.assertFalse(state.available)
        mock_warning.assert_called_once()

    @patch("poor_cli.rtk_integration.logger.warning")
    @patch("poor_cli.rtk_integration.shutil.which", return_value=None)
    def test_detect_rtk_disabled_skips_warning(self, mock_which, mock_warning):
        state = detect_rtk(enabled=False)
        self.assertFalse(state.available)
        mock_which.assert_not_called()
        mock_warning.assert_not_called()


class TestRTKWrapping(unittest.TestCase):
    def test_supported_command_detection(self):
        self.assertTrue(is_rtk_supported("git status"))
        self.assertTrue(is_rtk_supported("/usr/bin/git status"))
        self.assertFalse(is_rtk_supported("git status && echo done"))
        self.assertFalse(is_rtk_supported("python script.py"))
        self.assertFalse(is_rtk_supported("rtk git status"))

    def test_wrap_shell_command_prefixes_rtk(self):
        state = RTKState(enabled=True, tee_on_failure=True, binary_path="/opt/homebrew/bin/rtk")
        self.assertEqual(
            wrap_shell_command("git status", state),
            "/opt/homebrew/bin/rtk git status",
        )

    def test_wrap_shell_command_is_noop_when_unavailable(self):
        state = RTKState(enabled=True, tee_on_failure=True, binary_path=None)
        self.assertEqual(wrap_shell_command("git status", state), "git status")


class TestRepoPreferencesRTK(unittest.TestCase):
    def test_defaults_enable_rtk(self):
        prefs = RepoPreferences()
        self.assertTrue(prefs.rtk_enabled)
        self.assertTrue(prefs.rtk_tee_on_failure)

    def test_use_rtk_alias_maps_to_rtk_enabled(self):
        prefs = RepoPreferences.from_dict({"use_rtk": False, "rtk_tee_on_failure": False})
        self.assertFalse(prefs.rtk_enabled)
        self.assertFalse(prefs.rtk_tee_on_failure)


class TestEnhancedToolRegistryRTK(unittest.IsolatedAsyncioTestCase):
    async def test_bash_wraps_supported_commands(self):
        registry = EnhancedToolRegistry(config=MagicMock())
        registry._get_rtk_state = MagicMock(
            return_value=RTKState(enabled=True, tee_on_failure=True, binary_path="/opt/homebrew/bin/rtk")
        )
        with patch.object(ToolRegistryAsync, "bash", new_callable=AsyncMock, return_value="ok") as mock_bash:
            result = await registry.bash("git status", timeout=12)
        self.assertEqual(result, "ok")
        mock_bash.assert_awaited_once_with("/opt/homebrew/bin/rtk git status", timeout=12)

    async def test_bash_retries_raw_on_wrapped_failure(self):
        registry = EnhancedToolRegistry(config=MagicMock())
        registry._get_rtk_state = MagicMock(
            return_value=RTKState(enabled=True, tee_on_failure=True, binary_path="/opt/homebrew/bin/rtk")
        )
        wrapped_error = CommandExecutionError("/opt/homebrew/bin/rtk git status", "failed", return_code=1)
        with patch.object(
            ToolRegistryAsync,
            "bash",
            new_callable=AsyncMock,
            side_effect=[wrapped_error, "raw output"],
        ) as mock_bash:
            result = await registry.bash("git status")
        self.assertEqual(result, "raw output")
        self.assertEqual(
            mock_bash.await_args_list,
            [
                call("/opt/homebrew/bin/rtk git status", timeout=60),
                call("git status", timeout=60),
            ],
        )

    async def test_bash_skips_retry_when_disabled(self):
        registry = EnhancedToolRegistry(config=MagicMock())
        registry._get_rtk_state = MagicMock(
            return_value=RTKState(enabled=False, tee_on_failure=True, binary_path="/opt/homebrew/bin/rtk")
        )
        with patch.object(ToolRegistryAsync, "bash", new_callable=AsyncMock, return_value="ok") as mock_bash:
            result = await registry.bash("git status")
        self.assertEqual(result, "ok")
        mock_bash.assert_awaited_once_with("git status", timeout=60)

    async def test_bash_propagates_wrapped_failure_when_retry_disabled(self):
        registry = EnhancedToolRegistry(config=MagicMock())
        registry._get_rtk_state = MagicMock(
            return_value=RTKState(enabled=True, tee_on_failure=False, binary_path="/opt/homebrew/bin/rtk")
        )
        wrapped_error = CommandExecutionError("/opt/homebrew/bin/rtk git status", "failed", return_code=1)
        with patch.object(
            ToolRegistryAsync,
            "bash",
            new_callable=AsyncMock,
            side_effect=wrapped_error,
        ) as mock_bash:
            with self.assertRaises(CommandExecutionError):
                await registry.bash("git status")
        mock_bash.assert_awaited_once_with("/opt/homebrew/bin/rtk git status", timeout=60)

if __name__ == "__main__":
    unittest.main()
