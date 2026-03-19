import subprocess
import sys
import unittest


class ServerImportTests(unittest.TestCase):
    def _run_import(self, statement: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-c", statement],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_import_server_then_compat(self) -> None:
        result = self._run_import(
            "import poor_cli.server; import poor_cli._server; print('ok')"
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("ok", result.stdout)

    def test_import_compat_then_server(self) -> None:
        result = self._run_import(
            "import poor_cli._server; import poor_cli.server; print('ok')"
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("ok", result.stdout)


if __name__ == "__main__":
    unittest.main()
