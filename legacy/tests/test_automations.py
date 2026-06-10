import json
import tempfile
import unittest
from pathlib import Path

from poor_cli.automations import (
    AutomationRule,
    CronTrigger,
    EventTrigger,
    PromptStep,
    ShellStep,
    SlashTrigger,
    ToolCallStep,
    execute_step,
    migrate_extensions,
    restore_migration,
    rule_matches_trigger,
)


class AutomationRuleTests(unittest.TestCase):
    def test_trigger_dispatch_matches_cron_event_and_slash(self) -> None:
        rule = AutomationRule(
            id="qa",
            name="QA",
            triggers=[
                CronTrigger("0 9 * * *"),
                EventTrigger("file.changed", {"path": "README.md"}),
                SlashTrigger("/qa", "Run QA"),
            ],
            steps=[PromptStep("Run QA.")],
        )

        self.assertTrue(rule_matches_trigger(rule, "cron", {"expression": "0 9 * * *"}))
        self.assertTrue(rule_matches_trigger(rule, "event", {"event": "file.changed", "path": "README.md"}))
        self.assertTrue(rule_matches_trigger(rule, "slash", {"command": "/qa"}))
        self.assertFalse(rule_matches_trigger(rule, "event", {"event": "file.changed", "path": "other.md"}))

    def test_step_execution_dispatches_prompt_tool_and_shell(self) -> None:
        calls: list[tuple[str, object]] = []

        def prompt_runner(prompt: str) -> str:
            calls.append(("prompt", prompt))
            return "prompt-ok"

        def tool_runner(tool: str, params: dict) -> str:
            calls.append(("tool", (tool, params)))
            return "tool-ok"

        def shell_runner(command: str, cwd: str | None) -> str:
            calls.append(("shell", (command, cwd)))
            return "shell-ok"

        self.assertEqual(
            execute_step(
                PromptStep("Review diff."),
                prompt_runner=prompt_runner,
                tool_runner=tool_runner,
                shell_runner=shell_runner,
            ),
            "prompt-ok",
        )
        self.assertEqual(
            execute_step(
                ToolCallStep("read_file", {"path": "README.md"}),
                prompt_runner=prompt_runner,
                tool_runner=tool_runner,
                shell_runner=shell_runner,
            ),
            "tool-ok",
        )
        self.assertEqual(
            execute_step(
                ShellStep("pytest", "."),
                prompt_runner=prompt_runner,
                tool_runner=tool_runner,
                shell_runner=shell_runner,
            ),
            "shell-ok",
        )
        self.assertEqual(
            calls,
            [
                ("prompt", "Review diff."),
                ("tool", ("read_file", {"path": "README.md"})),
                ("shell", ("pytest", ".")),
            ],
        )

    def test_migration_round_trip_idempotent_dry_run_and_restore(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            state = root / ".poor-cli"
            state.mkdir()
            (state / "custom_commands.json").write_text(
                json.dumps({"commands": [{"name": "fix", "description": "Fix it", "template": "Fix {{args}}"}]}),
                encoding="utf-8",
            )
            (state / "workflow_templates.json").write_text(
                json.dumps(
                    {
                        "workflows": [
                            {
                                "name": "release",
                                "description": "Release",
                                "promptScaffold": "Draft release notes.",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (state / "automations.json").write_text(
                json.dumps(
                    {
                        "automations": [
                            {
                                "automationId": "daily",
                                "name": "Daily",
                                "prompt": "Run daily checks.",
                                "schedule": {"kind": "daily", "hour": 9, "minute": 30},
                                "enabled": True,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            dry_run = migrate_extensions(root, dry_run=True)
            self.assertFalse((state / "backup-pre-064").exists())
            self.assertEqual(dry_run.rule_count, 3)

            result = migrate_extensions(root)
            self.assertTrue(result.migrated)
            self.assertEqual(result.rule_count, 3)
            self.assertTrue((state / "backup-pre-064" / "custom_commands.json").exists())

            payload = json.loads((state / "automations.json").read_text(encoding="utf-8"))
            rules = payload["rules"]
            self.assertEqual({rule["name"] for rule in rules}, {"fix", "release", "Daily"})
            self.assertEqual(
                {rule["triggers"][0]["type"] for rule in rules},
                {"slash", "cron"},
            )

            second = migrate_extensions(root)
            self.assertFalse(second.migrated)
            self.assertEqual(second.skipped_reason, "backup-exists")
            self.assertEqual(second.rule_count, 3)

            restored = restore_migration(root)
            self.assertTrue(restored.migrated)
            restored_payload = json.loads((state / "automations.json").read_text(encoding="utf-8"))
            self.assertIn("automations", restored_payload)


if __name__ == "__main__":
    unittest.main()
