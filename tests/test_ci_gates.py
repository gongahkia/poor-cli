from __future__ import annotations

from pathlib import Path

import bench.loc_gate as loc_gate

ROOT = Path(__file__).resolve().parents[1]


def test_loc_gate_default_documents_6000_cap() -> None:
    text = (ROOT / "bench" / "loc_gate.py").read_text(encoding="utf-8")

    assert "default=6000" in text


def test_ci_workflows_include_v6_gates() -> None:
    for path in (ROOT / ".github" / "workflows" / "ci.yml", ROOT / ".github" / "workflows" / "v6.yml"):
        text = path.read_text(encoding="utf-8")
        assert "python -m pytest --cov=src/poor_cli --cov-fail-under=60 tests/" in text
        assert "poor-cli doctor | tee doctor.txt" in text
        assert 'grep -q "graph:python: ok" doctor.txt' in text
        assert "tests/test_provider_adapters.py tests/test_providers.py tests/test_native_runner.py" in text
        assert "python bench/replay_determinism_gate.py" in text
        assert "python bench/loc_gate.py" in text
        assert "python bench/packaging_gate.py" in text
        assert "mkdocs build --strict" in text


def test_live_provider_marker_policy_is_registered_and_skipped_by_default() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    conftest = (ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")

    assert "live_provider" in pyproject
    assert "POOR_CLI_LIVE_PROVIDER_TESTS" in conftest
    assert "live provider tests require" in conftest


def test_packaging_and_replay_gate_scripts_exist() -> None:
    assert (ROOT / "bench" / "packaging_gate.py").exists()
    assert (ROOT / "bench" / "replay_determinism_gate.py").exists()
    assert callable(loc_gate.main)
