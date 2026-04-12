import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_line_budgets.py"


def write_lines(path: Path, count: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x = 1\n" * count, encoding="utf-8")


def test_script_fails_on_oversized_file_fixture(tmp_path: Path) -> None:
    write_lines(tmp_path / "poor_cli" / "core.py", 1_001)
    write_lines(tmp_path / "poor_cli" / "server" / "runtime.py", 1)
    write_lines(tmp_path / "poor_cli" / "config.py", 1)
    write_lines(tmp_path / "tests" / "huge_test.py", 3_000)
    write_lines(tmp_path / "vendor" / "huge_vendor.py", 3_000)
    write_lines(tmp_path / "generated" / "huge_generated.py", 3_000)
    write_lines(tmp_path / "poor_cli" / "schema_pb2.py", 3_000)

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(tmp_path)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "poor_cli/core.py 1001/1000 (+1)" in result.stderr
    assert "tests/huge_test.py" not in result.stderr
    assert "vendor/huge_vendor.py" not in result.stderr
    assert "generated/huge_generated.py" not in result.stderr
    assert "poor_cli/schema_pb2.py" not in result.stderr
