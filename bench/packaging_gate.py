from __future__ import annotations

import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    with TemporaryDirectory(prefix="poor-cli-package-") as temp:
        tmp = Path(temp)
        dist = tmp / "dist"
        build = subprocess.run(
            [sys.executable, "-m", "build", "--outdir", str(dist)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        if build.returncode != 0:
            print(build.stdout + build.stderr)
            return build.returncode
        wheels = sorted(dist.glob("poor_cli-*.whl"))
        if not wheels:
            print("no wheel built")
            return 1
        python, env_vars, install = _install_wheel(tmp, wheels[0])
        if install.returncode != 0:
            print(install.stdout + install.stderr)
            return install.returncode
        for args in (["--version"], ["--help"]):
            result = subprocess.run(
                [str(python), "-m", "poor_cli", *args],
                cwd=ROOT,
                env=env_vars,
                text=True,
                capture_output=True,
                check=False,
            )
            if result.returncode != 0:
                print(result.stdout + result.stderr)
                return result.returncode
    print("packaging gate passed")
    return 0


def _install_wheel(tmp: Path, wheel: Path) -> tuple[Path, dict[str, str] | None, subprocess.CompletedProcess[str]]:
    env = tmp / "venv"
    try:
        venv.create(env, with_pip=True)
    except Exception:
        target = tmp / "target"
        install = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--target", str(target), str(wheel)],
            text=True,
            capture_output=True,
            check=False,
        )
        if install.returncode != 0 and shutil.which("uv"):
            install = subprocess.run(
                ["uv", "pip", "install", "--target", str(target), str(wheel)],
                text=True,
                capture_output=True,
                check=False,
            )
        env_vars = {**os.environ, "PYTHONPATH": str(target)}
        return Path(sys.executable), env_vars, install
    python = env / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    install = subprocess.run([str(python), "-m", "pip", "install", str(wheel)], text=True, capture_output=True, check=False)
    return python, None, install


if __name__ == "__main__":
    raise SystemExit(main())
