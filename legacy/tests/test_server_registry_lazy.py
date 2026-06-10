from __future__ import annotations

import subprocess
import sys


def _run_python(code: str) -> str:
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return proc.stdout.strip()


def test_runtime_import_keeps_rpc_registry_lazy():
    stdout = _run_python(
        "from poor_cli.server.registry import REGISTRY; "
        "import poor_cli.server.runtime; "
        "print('initialize' in REGISTRY)"
    )
    assert stdout.splitlines()[-1] == "False"


def test_ensure_handler_for_method_registers_initialize():
    stdout = _run_python(
        "from poor_cli.server.registry import REGISTRY, ensure_handler_for_method; "
        "loaded = ensure_handler_for_method('initialize'); "
        "print(str(loaded) + '|' + str('initialize' in REGISTRY))"
    )
    assert stdout.splitlines()[-1] == "True|True"


def test_get_startup_state_prefers_tiny_handler_module():
    stdout = _run_python(
        "import poor_cli.server.registry as registry; "
        "loaded = registry.ensure_handler_for_method('getStartupState'); "
        "loaded_startup = any(name.endswith('.startup_state') for name in registry._LOADED_MODULES); "
        "loaded_status = any(name.endswith('.status') for name in registry._LOADED_MODULES); "
        "print(str(loaded) + '|' + str(loaded_startup) + '|' + str(loaded_status))"
    )
    assert stdout.splitlines()[-1] == "True|True|False"


def test_runtime_fast_path_get_startup_state_skips_handler_registry_load():
    stdout = _run_python(
        "import asyncio; "
        "import poor_cli.server.registry as registry; "
        "from poor_cli.server.runtime import PoorCLIServer; "
        "from poor_cli.server.types import JsonRpcMessage; "
        "server = PoorCLIServer(); "
        "response = asyncio.run(server.dispatch(JsonRpcMessage(id=1, method='getStartupState', params={}))); "
        "loaded_startup = any(name.endswith('.startup_state') for name in registry._LOADED_MODULES); "
        "print(str(isinstance(response.result, dict)) + '|' + str('getStartupState' in registry.REGISTRY) + '|' + str(loaded_startup))"
    )
    assert stdout.splitlines()[-1] == "True|False|False"
