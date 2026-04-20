import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seuss.commands.generate_cmd import run_generate
from seuss.commands.ingest_cmd import run_ingest
from seuss.commands.init_cmd import run_init
from seuss.commands.persona_cmd import run_persona_build


class GeneratePersonaTests(unittest.TestCase):
    def _setup(self, root: Path) -> Path:
        notes_dir = root / "data" / "notes"
        notes_dir.mkdir(parents=True, exist_ok=True)
        (notes_dir / "sample.md").write_text(
            "I think persona-aware generation should preserve voice style.",
            encoding="utf-8",
        )

        config_path = root / "seuss.yaml"
        run_init(config_path=config_path, force=False)
        run_ingest(
            config_path=config_path,
            source_name=None,
            direct_path=None,
            dry_run=False,
            rebuild=False,
        )
        return config_path

    def test_generate_with_persona_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_path = self._setup(root)
            workspace = root / ".seuss"

            run_persona_build(config_path=config_path, output_path=None)
            rc = run_generate(
                config_path=config_path,
                prompt="I think",
                level="hybrid",
                max_tokens=50,
                temperature=0.8,
                seed=42,
                save=True,
                use_persona=True,
                persona_path=None,
            )
            self.assertEqual(rc, 0)

            run_files = sorted((workspace / "runs").glob("*.json"))
            self.assertTrue(run_files)
            run_data = json.loads(run_files[-1].read_text(encoding="utf-8"))
            self.assertTrue(run_data.get("used_persona"))
            self.assertIsNotNone(run_data.get("persona_profile_id"))
            self.assertNotEqual(run_data.get("effective_prompt"), run_data.get("prompt"))

    def test_generate_with_persona_without_profile_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_path = self._setup(root)

            rc = run_generate(
                config_path=config_path,
                prompt="I think",
                level="hybrid",
                max_tokens=50,
                temperature=0.8,
                seed=42,
                save=False,
                use_persona=True,
                persona_path=None,
            )
            self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
