import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seuss.commands.eval_cmd import run_eval
from seuss.commands.ingest_cmd import run_ingest
from seuss.commands.init_cmd import run_init


class EvalSummaryTests(unittest.TestCase):
    def test_eval_summary_outputs_checks_and_report_contains_overall(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            notes = root / "data" / "notes"
            notes.mkdir(parents=True, exist_ok=True)
            (notes / "sample.md").write_text(
                "I think clear boundaries matter. In practice iterate and validate.",
                encoding="utf-8",
            )
            config_path = root / "seuss.yaml"
            run_init(config_path=config_path, force=False)
            run_ingest(config_path=config_path, source_name=None, dry_run=False, rebuild=False)

            output_path = root / ".seuss" / "evals" / "summary_eval.json"
            with redirect_stdout(io.StringIO()) as stdout:
                rc = run_eval(
                    config_path=config_path,
                    suite="summary_test",
                    seed=42,
                    output_path=output_path,
                    summary=True,
                )
            self.assertEqual(rc, 0)
            printed = stdout.getvalue()
            self.assertIn("overall_pass=", printed)
            self.assertIn("PASS", printed)

            report = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertIn("checks", report)
            self.assertIn("overall_pass", report)
            self.assertIn("persona_match_min", report["checks"])


if __name__ == "__main__":
    unittest.main()
