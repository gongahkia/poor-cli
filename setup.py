from __future__ import annotations

import os
import platform
import stat
from pathlib import Path

from distutils.errors import DistutilsSetupError
from setuptools import setup
from setuptools.command.build_py import build_py as _build_py

try:
    from wheel.bdist_wheel import bdist_wheel as _bdist_wheel
except ImportError:  # pragma: no cover
    _bdist_wheel = None


def _tui_binary_name() -> str:
    return "poor-cli-tui.exe" if os.name == "nt" else "poor-cli-tui"


def _platform_binary_tag() -> str:
    machine = platform.machine().lower().replace("amd64", "x86_64")
    system = platform.system().lower()
    if system == "darwin":
        return f"macos-{machine}"
    if system == "windows":
        return f"windows-{machine}"
    if system == "linux":
        return f"linux-{machine}"
    return f"{system}-{machine}"


def _built_tui_binary(project_root: Path) -> Path:
    return project_root / "poor-cli-tui" / "target" / "release" / _tui_binary_name()


class PoorCLIBuildPy(_build_py):
    def run(self) -> None:
        super().run()
        if getattr(self.distribution, "_poor_cli_building_wheel", False):
            self._bundle_tui_binary()

    def _bundle_tui_binary(self) -> None:
        project_root = Path(__file__).resolve().parent
        source = _built_tui_binary(project_root)
        if not source.is_file():
            raise DistutilsSetupError(
                "Missing built Rust TUI binary for wheel packaging. "
                "Run `cargo build --manifest-path poor-cli-tui/Cargo.toml --release --locked` "
                "before building the wheel."
            )

        target_dir = Path(self.build_lib) / "poor_cli" / "bin" / _platform_binary_tag()
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / _tui_binary_name()
        self.copy_file(str(source), str(target))
        os.chmod(
            target,
            source.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH,
        )


cmdclass = {"build_py": PoorCLIBuildPy}

if _bdist_wheel is not None:
    class PoorCLIBdistWheel(_bdist_wheel):
        def finalize_options(self) -> None:
            super().finalize_options()
            self.root_is_pure = False

        def run(self) -> None:
            self.distribution._poor_cli_building_wheel = True
            try:
                super().run()
            finally:
                self.distribution._poor_cli_building_wheel = False

    cmdclass["bdist_wheel"] = PoorCLIBdistWheel


setup(cmdclass=cmdclass)
