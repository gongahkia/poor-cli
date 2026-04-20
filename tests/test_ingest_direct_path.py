import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seuss.commands.ingest_cmd import run_ingest
from seuss.commands.init_cmd import run_init
from seuss.jsonl_store import read_jsonl


class IngestDirectPathTests(unittest.TestCase):
    def test_ingest_relative_md_file_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            md_dir = root / "external" / "notes"
            md_dir.mkdir(parents=True, exist_ok=True)
            md_path = md_dir / "voice.md"
            md_path.write_text(
                "I think direct ingestion should work from relative paths.",
                encoding="utf-8",
            )

            config_path = root / "seuss.yaml"
            self.assertEqual(run_init(config_path=config_path, force=False), 0)

            rel_path = os.path.relpath(md_path, Path.cwd())
            self.assertEqual(
                run_ingest(
                    config_path=config_path,
                    source_name=None,
                    direct_path=rel_path,
                    dry_run=False,
                    rebuild=True,
                ),
                0,
            )

            fragments = read_jsonl(root / ".seuss" / "corpus" / "fragments.jsonl")
            self.assertGreater(len(fragments), 0)
            self.assertTrue(any("relative paths" in row.get("text", "") for row in fragments))

    def test_ingest_relative_directory_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            docs_dir = root / "docs_source"
            docs_dir.mkdir(parents=True, exist_ok=True)
            (docs_dir / "a.md").write_text("I think directories should ingest.", encoding="utf-8")
            (docs_dir / "b.md").write_text("In practice this should include both files.", encoding="utf-8")

            config_path = root / "seuss.yaml"
            self.assertEqual(run_init(config_path=config_path, force=False), 0)

            rel_path = os.path.relpath(docs_dir, Path.cwd())
            self.assertEqual(
                run_ingest(
                    config_path=config_path,
                    source_name=None,
                    direct_path=rel_path,
                    dry_run=False,
                    rebuild=True,
                ),
                0,
            )

            fragments = read_jsonl(root / ".seuss" / "corpus" / "fragments.jsonl")
            self.assertGreater(len(fragments), 0)
            sources = {row.get("source") for row in fragments}
            self.assertEqual(len(sources), 1)


if __name__ == "__main__":
    unittest.main()
