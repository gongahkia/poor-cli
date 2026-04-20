import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seuss.commands.ingest_cmd import run_ingest
from seuss.commands.init_cmd import run_init
from seuss.commands.inspect_cmd import run_inspect


class InspectRedactionSummaryTests(unittest.TestCase):
    def test_inspect_summary_shows_redaction_totals(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            notes_dir = root / "data" / "notes"
            notes_dir.mkdir(parents=True, exist_ok=True)
            (notes_dir / "sample.md").write_text(
                "Contact me at test@example.com or +1 555 123 4567.",
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

            with redirect_stdout(io.StringIO()) as out:
                self.assertEqual(
                    run_inspect(config_path=config_path, mode=None, source=None, limit=20),
                    0,
                )
            printed = out.getvalue()
            self.assertIn("Redaction summary (last ingest)", printed)
            self.assertIn("emails=", printed)
            self.assertIn("phone_numbers=", printed)


if __name__ == "__main__":
    unittest.main()
