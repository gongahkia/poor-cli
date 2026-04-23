import tempfile
import unittest
from pathlib import Path

from poor_cli.state_portability import export_state, import_state, inspect_state_archive


class StatePortabilityTests(unittest.TestCase):
    def test_export_import_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home" / ".poor-cli"
            repo = root / "repo"
            (home / "memory").mkdir(parents=True)
            (home / "memory" / "one.md").write_text("---\nname: one\n---\n\nbody\n")
            (repo / ".poor-cli" / "context").mkdir(parents=True)
            (repo / ".poor-cli" / "context" / "MAP.md").write_text("# map\n")
            archive = root / "state.zip"
            exported = export_state(archive, home_state=home, repo_root=repo)
            self.assertIn("home/memory/one.md", exported.files)
            dest_home = root / "dest-home" / ".poor-cli"
            dest_repo = root / "dest-repo"
            imported = import_state(archive, home_state=dest_home, repo_root=dest_repo)
            self.assertTrue(imported.files)
            self.assertTrue((dest_home / "memory" / "one.md").exists())
            self.assertTrue((dest_repo / ".poor-cli" / "context" / "MAP.md").exists())

    def test_inspect_and_dry_run_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home" / ".poor-cli"
            repo = root / "repo"
            (home / "memory").mkdir(parents=True)
            (home / "memory" / "one.md").write_text("body\n")
            archive = root / "state.zip"
            exported = export_state(archive, home_state=home, repo_root=repo)
            self.assertIn("home/memory/one.md", exported.manifest["files"])
            inspected = inspect_state_archive(archive)
            self.assertIn("manifest.json", inspected.files)
            dest_home = root / "dest-home" / ".poor-cli"
            dry = import_state(archive, home_state=dest_home, repo_root=root / "dest-repo", dry_run=True)
            self.assertTrue(dry.files)
            self.assertFalse((dest_home / "memory" / "one.md").exists())


if __name__ == "__main__":
    unittest.main()
