import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seuss.commands.eval_cmd import run_eval
from seuss.commands.generate_cmd import run_generate
from seuss.commands.ingest_cmd import run_ingest
from seuss.commands.init_cmd import run_init
from seuss.commands.memory_cmd import run_memory_add
from seuss.commands.reset_cmd import run_reset_corpus, run_reset_workspace
from seuss.jsonl_store import read_jsonl


class ResetCommandTests(unittest.TestCase):
    def _bootstrap_workspace(self, root: Path) -> Path:
        notes_dir = root / "data" / "notes"
        notes_dir.mkdir(parents=True, exist_ok=True)
        (notes_dir / "sample.md").write_text(
            "I think reset should make experiments reproducible.",
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
        run_generate(
            config_path=config_path,
            prompt="I think",
            level="hybrid",
            max_tokens=30,
            temperature=0.8,
            seed=42,
            save=True,
        )
        run_eval(
            config_path=config_path,
            suite="reset_test",
            seed=42,
            output_path=None,
            summary=False,
        )
        run_memory_add(
            config_path=config_path,
            text="Keep this memory unless workspace reset is requested.",
            kind="style",
        )
        return config_path

    def test_reset_corpus_requires_yes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_path = self._bootstrap_workspace(root)
            rc = run_reset_corpus(config_path=config_path, yes=False, keep_runs=False, keep_evals=False)
            self.assertEqual(rc, 1)

    def test_reset_corpus_clears_fragments_and_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_path = self._bootstrap_workspace(root)
            workspace = root / ".seuss"

            rc = run_reset_corpus(config_path=config_path, yes=True, keep_runs=False, keep_evals=False)
            self.assertEqual(rc, 0)

            fragments = read_jsonl(workspace / "corpus" / "fragments.jsonl")
            self.assertEqual(fragments, [])
            self.assertFalse(list((workspace / "runs").glob("*.json")))
            self.assertFalse(list((workspace / "evals").glob("*.json")))

    def test_reset_workspace_reinitializes_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_path = self._bootstrap_workspace(root)
            workspace = root / ".seuss"

            rc = run_reset_workspace(config_path=config_path, yes=True)
            self.assertEqual(rc, 0)

            self.assertTrue((workspace / "corpus" / "fragments.jsonl").exists())
            self.assertTrue((workspace / "memory" / "memories.jsonl").exists())
            self.assertTrue((workspace / "training_queue.jsonl").exists())
            self.assertTrue((workspace / "approved_training.jsonl").exists())

            fragments = read_jsonl(workspace / "corpus" / "fragments.jsonl")
            memories = read_jsonl(workspace / "memory" / "memories.jsonl")
            self.assertEqual(fragments, [])
            self.assertEqual(memories, [])


if __name__ == "__main__":
    unittest.main()
