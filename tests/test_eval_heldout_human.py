import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seuss.commands.eval_cmd import run_eval
from seuss.commands.ingest_cmd import run_ingest
from seuss.commands.init_cmd import run_init
from seuss.jsonl_store import read_jsonl, write_jsonl


class EvalHeldoutHumanTests(unittest.TestCase):
    def test_eval_requires_human_origin_heldout_when_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            notes_dir = root / "data" / "notes"
            notes_dir.mkdir(parents=True, exist_ok=True)
            (notes_dir / "sample.md").write_text(
                "I think heldout validation should enforce human-origin rows.",
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

            fragments_path = root / ".seuss" / "corpus" / "fragments.jsonl"
            rows = read_jsonl(fragments_path)
            mutated = []
            for row in rows:
                updated = dict(row)
                if updated.get("split") == "eval":
                    updated["provenance"] = "ai_generated"
                mutated.append(updated)
            write_jsonl(fragments_path, mutated)

            self.assertEqual(
                run_eval(
                    config_path=config_path,
                    suite="heldout_human_check",
                    seed=42,
                    output_path=root / ".seuss" / "evals" / "heldout_human_check.json",
                    summary=True,
                    fail_on_thresholds=False,
                ),
                1,
            )


if __name__ == "__main__":
    unittest.main()
