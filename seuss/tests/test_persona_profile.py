import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seuss.commands.ingest_cmd import run_ingest
from seuss.commands.init_cmd import run_init
from seuss.commands.memory_cmd import run_memory_add
from seuss.commands.persona_cmd import run_persona_build, run_persona_show


class PersonaProfileTests(unittest.TestCase):
    def test_build_and_show_persona_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            notes_dir = root / "data" / "notes"
            notes_dir.mkdir(parents=True, exist_ok=True)
            (notes_dir / "sample.md").write_text(
                "I think clean boundaries help. In practice we optimize after measurement.",
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
                    rebuild=False,
                ),
                0,
            )
            self.assertEqual(
                run_memory_add(
                    config_path=config_path,
                    text="Prefers direct, implementation-focused responses.",
                    kind="style",
                ),
                0,
            )

            profile_path = root / ".seuss" / "memory" / "persona_profile.json"
            self.assertEqual(
                run_persona_build(config_path=config_path, output_path=profile_path),
                0,
            )
            self.assertTrue(profile_path.exists())

            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            self.assertIn("voice", profile)
            self.assertIn("lexical", profile)
            self.assertIn("memory_hints", profile)

            with redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(
                    run_persona_show(config_path=config_path, input_path=profile_path),
                    0,
                )
            out = stdout.getvalue()
            self.assertIn("sentence_length_bucket=", out)
            self.assertIn("top_words=", out)


if __name__ == "__main__":
    unittest.main()
