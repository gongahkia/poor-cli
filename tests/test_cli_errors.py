import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


def _clean_env(home: str) -> dict[str, str]:
    env = dict(os.environ)
    env["HOME"] = home
    env.pop("GEMINI_API_KEY", None)
    env.pop("OPENAI_API_KEY", None)
    env.pop("ANTHROPIC_API_KEY", None)
    return env


class CliErrorRenderingTests(unittest.TestCase):
    def test_exec_missing_api_key_exits_without_traceback(self) -> None:
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
            self.assertIn("No API key found for provider: gemini", combined)
            self.assertIn("Set `GEMINI_API_KEY`", combined)

    def test_bridge_invalid_invite_exits_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "home"
            stubs = Path(tmpdir) / "stubs"
            aiortc_package = stubs / "aiortc"
            home.mkdir(parents=True, exist_ok=True)
            aiortc_package.mkdir(parents=True, exist_ok=True)
            (stubs / "aiohttp.py").write_text("class ClientSession: pass\n", encoding="utf-8")
            (aiortc_package / "__init__.py").write_text(
                textwrap.dedent(
                    """
                    class RTCConfiguration:
                        def __init__(self, *args, **kwargs):
                            pass

                    class RTCIceServer:
                        def __init__(self, *args, **kwargs):
                            pass

                    class RTCPeerConnection:
                        def __init__(self, *args, **kwargs):
                            pass

                    class RTCSessionDescription:
                        def __init__(self, *args, **kwargs):
                            pass
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            env = _clean_env(str(home))
            env["PYTHONPATH"] = (
                f"{stubs}{os.pathsep}{env['PYTHONPATH']}"
                if env.get("PYTHONPATH")
                else str(stubs)
            )

            result = subprocess.run(
                [sys.executable, "-m", "poor_cli", "server", "--bridge", "--invite", "invalid"],
                cwd=Path(__file__).resolve().parent.parent,
                env=env,
                capture_output=True,
                text=True,
            )

            combined = f"{result.stdout}\n{result.stderr}"
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("Traceback", combined)
            self.assertIn("Invalid invite code", combined)
            self.assertIn("Generate a fresh invite", combined)


if __name__ == "__main__":
    unittest.main()
