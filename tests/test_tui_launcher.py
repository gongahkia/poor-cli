import io
import json
import os
import stat
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from poor_cli import tui_launcher


def _make_executable(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


class TuiLauncherTests(unittest.TestCase):
    def test_resolve_tui_binary_prefers_packaged_binary_over_path_when_repo_is_stale(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            package_root = root / "poor_cli"
            repo_root = root / "repo"
            repo_binary = repo_root / "poor-cli-tui" / "target" / "release" / tui_launcher.tui_executable_name()
            packaged_binary = (
                package_root
                / "bin"
                / f"{sys_platform_tag()}-{machine_tag()}"
                / tui_launcher.tui_executable_name()
            )
            path_binary = root / "bin" / tui_launcher.tui_executable_name()

            _make_executable(repo_binary)
            _make_executable(packaged_binary)
            _make_executable(path_binary)
            (repo_root / "poor-cli-tui" / "src").mkdir(parents=True, exist_ok=True)
            watched_source = repo_root / "poor-cli-tui" / "src" / "main.rs"
            watched_source.write_text("fn main() {}\n", encoding="utf-8")
            stale_mtime = repo_binary.stat().st_mtime - 10
            os.utime(repo_binary, (stale_mtime, stale_mtime))

            with mock.patch.object(tui_launcher, "_package_root", return_value=package_root), mock.patch.object(
                tui_launcher, "repo_root", return_value=repo_root
            ), mock.patch("shutil.which", return_value=str(path_binary)):
                resolved, source = tui_launcher.resolve_tui_binary()

            self.assertEqual(resolved.resolve(), packaged_binary.resolve())
            self.assertEqual(source, "package")

    def test_resolve_tui_binary_uses_fresh_repo_binary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            repo_root = root / "repo"
            package_root = root / "poor_cli"
            repo_binary = repo_root / "poor-cli-tui" / "target" / "release" / tui_launcher.tui_executable_name()
            _make_executable(repo_binary)
            cargo_toml = repo_root / "poor-cli-tui" / "Cargo.toml"
            cargo_lock = repo_root / "poor-cli-tui" / "Cargo.lock"
            src_file = repo_root / "poor-cli-tui" / "src" / "main.rs"
            for watched in (cargo_toml, cargo_lock, src_file):
                watched.parent.mkdir(parents=True, exist_ok=True)
                watched.write_text("data\n", encoding="utf-8")
                fresh_time = repo_binary.stat().st_mtime - 10
                os.utime(watched, (fresh_time, fresh_time))

            with mock.patch.object(tui_launcher, "_package_root", return_value=package_root), mock.patch.object(
                tui_launcher, "repo_root", return_value=repo_root
            ), mock.patch("shutil.which", return_value=None):
                resolved, source = tui_launcher.resolve_tui_binary()

            self.assertEqual(resolved, repo_binary)
            self.assertEqual(source, "repo")

    def test_inspect_tui_installation_reports_selected_packaged_launcher(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            package_root = root / "poor_cli"
            packaged_binary = (
                package_root
                / "bin"
                / f"{sys_platform_tag()}-{machine_tag()}"
                / tui_launcher.tui_executable_name()
            )
            _make_executable(packaged_binary)

            with mock.patch.object(tui_launcher, "_package_root", return_value=package_root), mock.patch.object(
                tui_launcher, "repo_root", return_value=root / "repo"
            ), mock.patch("shutil.which", return_value=None), mock.patch.dict(os.environ, {}, clear=False):
                payload = tui_launcher.inspect_tui_installation()

            self.assertEqual(payload["selectedLauncher"]["source"], "package")
            self.assertEqual(
                Path(payload["selectedLauncher"]["path"]).resolve(),
                packaged_binary.resolve(),
            )

    def test_run_install_info_mode_renders_human_and_json_output(self) -> None:
        payload = {
            "version": "1.2.3",
            "platform": "linux",
            "machine": "x86_64",
            "tuiExecutableName": "poor-cli-tui",
            "selectedLauncher": {"source": "package", "path": "/tmp/poor-cli-tui"},
            "envOverride": {"configured": False, "path": None, "usable": False},
            "repoBinary": {"path": "/repo/bin", "exists": False, "usable": False, "fresh": False},
            "packagedCandidates": [{"path": "/tmp/poor-cli-tui", "exists": True, "usable": True}],
            "pathBinary": {"path": None, "usable": False},
            "repoLauncherScript": {"path": "/repo/run_tui.sh", "exists": False},
        }

        with mock.patch.object(tui_launcher, "inspect_tui_installation", return_value=payload):
            text_buffer = io.StringIO()
            with redirect_stdout(text_buffer):
                exit_code = tui_launcher.run_install_info_mode([])
            self.assertEqual(exit_code, 0)
            self.assertIn("Resolved launcher: package -> /tmp/poor-cli-tui", text_buffer.getvalue())

            json_buffer = io.StringIO()
            with redirect_stdout(json_buffer):
                exit_code = tui_launcher.run_install_info_mode(["--json"])
            self.assertEqual(exit_code, 0)
            rendered = json.loads(json_buffer.getvalue())
            self.assertEqual(rendered["selectedLauncher"]["source"], "package")


def machine_tag() -> str:
    return tui_launcher.platform.machine().lower().replace("amd64", "x86_64")


def sys_platform_tag() -> str:
    return tui_launcher.sys.platform.lower()


if __name__ == "__main__":
    unittest.main()
