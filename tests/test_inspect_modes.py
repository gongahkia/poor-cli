import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seuss.commands.generate_cmd import run_generate
from seuss.commands.ingest_cmd import run_ingest
from seuss.commands.init_cmd import run_init
from seuss.commands.inspect_cmd import run_inspect
from seuss.commands.memory_cmd import run_memory_add


class InspectModesTests(unittest.TestCase):
    def test_inspect_queue_and_runs_modes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "data" / "notes").mkdir(parents=True, exist_ok=True)
            (root / "data" / "notes" / "sample.md").write_text(
                "I think we should validate behavior. In practice we iterate.",
                encoding="utf-8",
            )

            config_path = root / "seuss.yaml"
            self.assertEqual(run_init(config_path=config_path, force=False), 0)
            self.assertEqual(
                run_ingest(
                    config_path=config_path,
                    source_name=None,
                    dry_run=False,
                    rebuild=False,
                ),
                0,
            )
            self.assertEqual(
                run_generate(
                    config_path=config_path,
                    prompt="I think",
                    level="hybrid",
                    max_tokens=32,
                    temperature=0.8,
                    seed=42,
                    save=True,
                ),
                0,
            )
            self.assertEqual(run_memory_add(config_path=config_path, text="Prefers direct replies.", kind="style"), 0)

            with redirect_stdout(io.StringIO()) as queue_stdout:
                self.assertEqual(
                    run_inspect(config_path=config_path, mode="queue", source=None, limit=10),
                    0,
                )
            self.assertIn("Queue records", queue_stdout.getvalue())

            with redirect_stdout(io.StringIO()) as runs_stdout:
                self.assertEqual(
                    run_inspect(config_path=config_path, mode="runs", source=None, limit=10),
                    0,
                )
            self.assertIn("Run files", runs_stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
