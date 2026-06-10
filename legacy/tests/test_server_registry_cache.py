from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _run_python(code: str, *, env: dict[str, str]) -> str:
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return proc.stdout.strip()


def test_registry_writes_cache_file(tmp_path: Path) -> None:
    cache_path = tmp_path / "registry-index.json"
    env = os.environ.copy()
    env["POORCLI_SERVER_REGISTRY_CACHE_PATH"] = str(cache_path)
    env["POORCLI_SERVER_REGISTRY_STATIC_INDEX_PATH"] = str(tmp_path / "missing-static-index.json")
    stdout = _run_python(
        "from poor_cli.server.registry import ensure_handler_for_method; "
        "ensure_handler_for_method('initialize'); "
        "import os; "
        "print(str(os.path.exists(os.environ['POORCLI_SERVER_REGISTRY_CACHE_PATH'])))",
        env=env,
    )
    assert stdout.splitlines()[-1] == "True"


def test_registry_uses_cache_without_ast_parse(tmp_path: Path) -> None:
    cache_path = tmp_path / "registry-index.json"
    env = os.environ.copy()
    env["POORCLI_SERVER_REGISTRY_CACHE_PATH"] = str(cache_path)
    env["POORCLI_SERVER_REGISTRY_STATIC_INDEX_PATH"] = str(tmp_path / "missing-static-index.json")

    _run_python(
        "from poor_cli.server.registry import ensure_handler_for_method; "
        "print(str(ensure_handler_for_method('initialize')))",
        env=env,
    )

    stdout = _run_python(
        "import ast; "
        "import poor_cli.server.registry as registry; "
        "ast.parse = (lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError('blocked'))); "
        "print(str(registry.ensure_handler_for_method('initialize')) + '|' + str('initialize' in registry.REGISTRY))",
        env=env,
    )
    assert stdout.splitlines()[-1] == "True|True"


def test_registry_uses_static_index_without_cache() -> None:
    env = os.environ.copy()
    env["POORCLI_SERVER_REGISTRY_CACHE_PATH"] = "/dev/null/registry-index.json"
    stdout = _run_python(
        "import ast; "
        "import poor_cli.server.registry as registry; "
        "ast.parse = (lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError('blocked'))); "
        "loaded = registry.ensure_handler_for_method('initialize'); "
        "print(str(loaded) + '|' + str('initialize' in registry.REGISTRY) + '|' + str(registry._INDEX_SOURCE))",
        env=env,
    )
    assert stdout.splitlines()[-1] == "True|True|static"
