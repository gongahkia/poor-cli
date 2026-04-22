import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seuss.commands.eval_cmd import run_eval
from seuss.commands.generate_cmd import run_generate
from seuss.commands.ingest_cmd import run_ingest
from seuss.commands.init_cmd import run_init
from seuss.jsonl_store import read_jsonl


class Phase1WorkflowTests(unittest.TestCase):
    def test_init_ingest_generate_eval_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            notes_dir = root / "data" / "notes"
            notes_dir.mkdir(parents=True, exist_ok=True)
            (notes_dir / "sample.md").write_text(
                "I think clear contracts matter. In practice, measure before optimizing.",
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

            workspace = root / ".seuss"
            fragments = read_jsonl(workspace / "corpus" / "fragments.jsonl")
            self.assertGreater(len(fragments), 0)
            self.assertTrue(any(row.get("split") == "train" for row in fragments))

            self.assertEqual(
                run_generate(
                    config_path=config_path,
                    prompt="I think",
                    level="hybrid",
                    max_tokens=40,
                    temperature=0.8,
                    seed=123,
                    save=True,
                ),
                0,
            )
            self.assertTrue(list((workspace / "runs").glob("*.json")))

            eval_report = workspace / "evals" / "phase1_smoke.json"
            self.assertEqual(
                run_eval(
                    config_path=config_path,
                    suite="phase1_smoke",
                    seed=123,
                    output_path=eval_report,
                ),
                0,
            )
            report = json.loads(eval_report.read_text(encoding="utf-8"))
            self.assertIn("metrics", report)
            self.assertIn("persona_match_score", report["metrics"])


if __name__ == "__main__":
    unittest.main()
