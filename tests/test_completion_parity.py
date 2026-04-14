import re
import unittest
from pathlib import Path


ROOT_COMMANDS = {
    "help",
    "version",
    "tui",
    "install",
    "install-info",
    "exec",
    "task",
    "automation",
    "github-task",
    "skills",
    "commands",
    "server",
    "telegram",
    "watch",
    "deploy",
    "preview",
    "review-pr",
    "agent",
}

TASK_SUBCOMMANDS = {"create", "list", "show", "start", "wait", "approve", "cancel", "retry", "replay", "run"}
AUTOMATION_SUBCOMMANDS = {"create", "list", "show", "enable", "disable", "run-now", "run-due", "serve", "history", "replay", "migrate"}
AGENT_SUBCOMMANDS = {"start", "list", "logs", "result", "cancel", "run"}


class CompletionParityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parent.parent
        self.bash = (self.repo_root / "completions" / "poor_cli.bash").read_text(encoding="utf-8")
        self.fish = (self.repo_root / "completions" / "poor_cli.fish").read_text(encoding="utf-8")
        self.zsh = (self.repo_root / "completions" / "poor_cli.zsh").read_text(encoding="utf-8")

    def test_bash_completion_matches_root_surface(self) -> None:
        match = re.search(r'local root_commands="([^"]+)"', self.bash)
        self.assertIsNotNone(match, "bash completion must define root_commands")
        commands = set((match.group(1) if match else "").split())
        self.assertTrue(ROOT_COMMANDS.issubset(commands))
        self.assertNotIn("/help", self.bash, "legacy slash-command completions should not remain")

    def test_fish_completion_matches_root_surface(self) -> None:
        commands = set()
        for line in self.fish.splitlines():
            if "__fish_use_subcommand" not in line:
                continue
            match = re.search(r'-a "([^"]+)"', line)
            if match:
                commands.add(match.group(1))
        self.assertTrue(ROOT_COMMANDS.issubset(commands))
        self.assertNotIn("/help", self.fish, "legacy slash-command completions should not remain")

    def test_zsh_completion_matches_root_surface(self) -> None:
        commands = set()
        in_root = False
        for line in self.zsh.splitlines():
            stripped = line.strip()
            if stripped == "root_commands=(":
                in_root = True
                continue
            if in_root and stripped == ")":
                break
            if not in_root:
                continue
            match = re.match(r"'([^:']+):", stripped)
            if match:
                commands.add(match.group(1))
        self.assertTrue(ROOT_COMMANDS.issubset(commands))
        self.assertNotIn("/help", self.zsh, "legacy slash-command completions should not remain")

    def test_nested_command_sets_are_present_in_all_completion_surfaces(self) -> None:
        for command in TASK_SUBCOMMANDS:
            self.assertIn(command, self.bash)
            self.assertIn(command, self.fish)
            self.assertIn(command, self.zsh)
        for command in AUTOMATION_SUBCOMMANDS:
            self.assertIn(command, self.bash)
            self.assertIn(command, self.fish)
            self.assertIn(command, self.zsh)
        for command in AGENT_SUBCOMMANDS:
            self.assertIn(command, self.bash)
            self.assertIn(command, self.fish)
            self.assertIn(command, self.zsh)


if __name__ == "__main__":
    unittest.main()
