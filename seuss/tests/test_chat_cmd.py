import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seuss.commands.chat_cmd import run_chat
from seuss.commands.ingest_cmd import run_ingest
from seuss.commands.init_cmd import run_init
from seuss.jsonl_store import read_jsonl


class ChatCommandTests(unittest.TestCase):
    def _bootstrap(self, root: Path) -> Path:
        notes_dir = root / "data" / "notes"
        notes_dir.mkdir(parents=True, exist_ok=True)
        (notes_dir / "sample.md").write_text(
            "I think chat mode should be simple. In practice we can iterate quickly.",
            encoding="utf-8",
        )

        config_path = root / "seuss.yaml"
        self.assertEqual(run_init(config_path=config_path, force=False), 0)
        self.assertEqual(
            run_ingest(
                config_path=config_path,
                source_name=None,
                direct_path=None,
                dry_run=False,
                rebuild=True,
            ),
            0,
        )
        return config_path

    def test_chat_captures_memory_and_generates_response(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_path = self._bootstrap(root)

            with patch("builtins.input", side_effect=["I prefer concise answers."]):
                with redirect_stdout(io.StringIO()) as out:
                    self.assertEqual(
                        run_chat(
                            config_path=config_path,
                            level="hybrid",
                            max_tokens=40,
                            temperature=0.8,
                            seed=7,
                            save=False,
                            use_persona=False,
                            persona_path=None,
                            refresh_persona_every=3,
                            max_turns=1,
                        ),
                        0,
                    )

            printed = out.getvalue()
            self.assertIn("assistant>", printed)
            memories = read_jsonl(root / ".seuss" / "memory" / "memories.jsonl")
            self.assertTrue(any(row.get("text") == "I prefer concise answers." for row in memories))

    def test_chat_queues_training_when_policy_requires_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_path = self._bootstrap(root)

            cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            cfg["adaptation"]["live_training_data"]["enabled"] = True
            cfg["adaptation"]["live_training_data"]["require_explicit_approval"] = True
            config_path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")

            with patch("builtins.input", side_effect=["Queue this message."]):
                self.assertEqual(
                    run_chat(
                        config_path=config_path,
                        level="hybrid",
                        max_tokens=32,
                        temperature=0.8,
                        seed=11,
                        save=False,
                        use_persona=False,
                        persona_path=None,
                        refresh_persona_every=3,
                        max_turns=1,
                    ),
                    0,
                )

            queue = read_jsonl(root / ".seuss" / "training_queue.jsonl")
            self.assertGreater(len(queue), 0)
            self.assertTrue(any(row.get("approval_status") == "pending" for row in queue))

    def test_chat_builds_persona_when_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_path = self._bootstrap(root)

            with patch("builtins.input", side_effect=["Please adapt to my style."]):
                self.assertEqual(
                    run_chat(
                        config_path=config_path,
                        level="hybrid",
                        max_tokens=32,
                        temperature=0.8,
                        seed=5,
                        save=False,
                        use_persona=True,
                        persona_path=None,
                        refresh_persona_every=1,
                        max_turns=1,
                    ),
                    0,
                )

            profile_path = root / ".seuss" / "memory" / "persona_profile.json"
            self.assertTrue(profile_path.exists())


if __name__ == "__main__":
    unittest.main()
