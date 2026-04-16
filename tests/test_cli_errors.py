import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from poor_cli.config import Config


def _clean_env(home: str) -> dict[str, str]:
    env = dict(os.environ)
    env["HOME"] = home
    env.pop("GEMINI_API_KEY", None)
    env.pop("OPENAI_API_KEY", None)
    env.pop("ANTHROPIC_API_KEY", None)
    return env


class CliErrorRenderingTests(unittest.TestCase):
    def test_exec_missing_api_key_exits_without_traceback(self) -> None:
        cfg = Config()
        expected_provider = cfg.model.provider
        expected_env = cfg.model.providers[expected_provider].api_key_env_var

        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            keys_dir = home / ".poor-cli" / "keys"
            keys_dir.mkdir(parents=True, exist_ok=True)
            (keys_dir / "encrypted_keys.json").write_text(
                '{"gemini": {"encrypted_key": "not-base64", "created_at": "", "last_rotated": "", "metadata": {}}}',
                encoding="utf-8",
            )

            result = subprocess.run(
                [sys.executable, "-m", "poor_cli", "exec", "--plan-only", "--prompt", "test"],
                cwd=Path(__file__).resolve().parent.parent,
                env=_clean_env(str(home)),
                capture_output=True,
                text=True,
            )

            combined = f"{result.stdout}\n{result.stderr}"
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("Traceback", combined)
            self.assertNotIn("Failed to decrypt API key", combined)
            self.assertIn(f"No API key found for provider: {expected_provider}", combined)
            self.assertIn(f"Set `{expected_env}`", combined)

if __name__ == "__main__":
    unittest.main()
