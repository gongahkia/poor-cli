import json
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seuss.commands.eval_cmd import run_eval
from seuss.commands.ingest_cmd import run_ingest
from seuss.commands.init_cmd import run_init


class EvalProvenanceTests(unittest.TestCase):
    def test_eval_report_contains_provenance_checks(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            notes_dir = root / "data" / "notes"
            notes_dir.mkdir(parents=True, exist_ok=True)
            (notes_dir / "sample.md").write_text(
                "I think provenance checks should be visible in eval reports.",
                encoding="utf-8",
            )

            config_path = root / "seuss.yaml"
            self.assertEqual(run_init(config_path=config_path, force=False), 0)
            cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            cfg["evaluation"]["heldout_required"] = False
            config_path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
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

            report_path = root / ".seuss" / "evals" / "prov_eval.json"
            self.assertEqual(
                run_eval(
                    config_path=config_path,
                    suite="prov_test",
                    seed=42,
                    output_path=report_path,
                    summary=True,
                ),
                0,
            )

            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertIn("provenance_checks", report)
            self.assertIn("train", report["provenance_checks"])
            self.assertIn("human_ratio", report["provenance_checks"]["train"])


if __name__ == "__main__":
    unittest.main()
