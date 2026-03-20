"""Rust TUI launcher resolution and install inspection helpers."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional, Sequence

from . import __version__


def tui_executable_name() -> str:
    return "poor-cli-tui.exe" if os.name == "nt" else "poor-cli-tui"


def is_usable_binary(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def _package_root() -> Path:
    return Path(__file__).resolve().parent


def repo_root() -> Path:
    return _package_root().parent


def repo_tui_binary_path(root: Optional[Path] = None) -> Path:
    resolved_root = root or repo_root()
    return resolved_root / "poor-cli-tui" / "target" / "release" / tui_executable_name()


def repo_binary_is_fresh(root: Path, binary: Path) -> bool:
    if not is_usable_binary(binary):
        return False

    try:
        binary_mtime = binary.stat().st_mtime
    except OSError:
        return False

    watched_paths = [
        root / "poor-cli-tui" / "Cargo.toml",
        root / "poor-cli-tui" / "Cargo.lock",
    ]
    src_dir = root / "poor-cli-tui" / "src"
    watched_paths.extend(path for path in src_dir.rglob("*") if path.is_file())

    try:
        return not any(path.stat().st_mtime > binary_mtime for path in watched_paths if path.exists())
    except OSError:
        return False


def run_tui_from_repo(argv: list[str]) -> int:
    root = repo_root()
    script = root / "run_tui.sh"
    if not script.is_file():
        return 1
    return subprocess.call([str(script), *argv], cwd=str(root))


def iter_packaged_tui_candidates() -> list[Path]:
    package_root = _package_root()
    executable = tui_executable_name()
    machine = platform.machine().lower().replace("amd64", "x86_64")
    platform_key = sys.platform.lower()
    platform_tags = [platform_key, f"{platform_key}-{machine}"]

    if sys.platform == "darwin":
        platform_tags.extend(["macos", f"macos-{machine}"])
    elif sys.platform.startswith("linux"):
        platform_tags.extend(["linux", f"linux-{machine}"])
    elif os.name == "nt":
        platform_tags.extend(["windows", f"windows-{machine}"])

    candidates = [package_root / "bin" / executable]
    candidates.extend(package_root / "bin" / tag / executable for tag in platform_tags)

    deduped: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def resolve_env_tui_binary() -> Optional[Path]:
    raw_value = os.environ.get("POOR_CLI_TUI_BIN", "").strip()
    if not raw_value:
        return None
    candidate = Path(raw_value).expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    candidate = candidate.resolve()
    if not is_usable_binary(candidate):
        return None
    return candidate


def resolve_packaged_tui_binary() -> Optional[Path]:
    for candidate in iter_packaged_tui_candidates():
        if is_usable_binary(candidate):
            return candidate
    return None


def resolve_path_tui_binary() -> Optional[Path]:
    binary = shutil.which(tui_executable_name())
    if binary is None:
        return None
    return Path(binary).resolve()


def resolve_tui_binary() -> tuple[Optional[Path], Optional[str]]:
    env_binary = resolve_env_tui_binary()
    if env_binary is not None:
        return env_binary, "env"

    root = repo_root()
    repo_binary = repo_tui_binary_path(root)
    if repo_binary_is_fresh(root, repo_binary):
        return repo_binary, "repo"

    packaged_binary = resolve_packaged_tui_binary()
    if packaged_binary is not None:
        return packaged_binary, "package"

    path_binary = resolve_path_tui_binary()
    if path_binary is not None:
        return path_binary, "path"

    return None, None


def run_tui_binary(argv: list[str]) -> int:
    binary, _source = resolve_tui_binary()
    if binary is None:
        return 1
    os.execv(str(binary), [str(binary), *argv])
    return 1


def inspect_tui_installation() -> dict[str, Any]:
    root = repo_root()
    repo_binary = repo_tui_binary_path(root)
    env_override = os.environ.get("POOR_CLI_TUI_BIN", "").strip()
    env_binary = resolve_env_tui_binary()
    path_binary = resolve_path_tui_binary()
    selected_binary, selected_source = resolve_tui_binary()
    packaged_candidates = iter_packaged_tui_candidates()
    run_tui_script = root / "run_tui.sh"
    selected_launcher = None
    if selected_binary is not None and selected_source is not None:
        selected_launcher = {
            "source": selected_source,
            "path": str(selected_binary),
        }
    elif run_tui_script.is_file():
        selected_launcher = {
            "source": "repo-script",
            "path": str(run_tui_script),
        }

    return {
        "version": __version__,
        "platform": sys.platform,
        "machine": platform.machine(),
        "tuiExecutableName": tui_executable_name(),
        "selectedLauncher": selected_launcher,
        "envOverride": {
            "configured": bool(env_override),
            "path": env_override or None,
            "usable": env_binary is not None,
        },
        "repoBinary": {
            "path": str(repo_binary),
            "exists": repo_binary.is_file(),
            "usable": is_usable_binary(repo_binary),
            "fresh": repo_binary_is_fresh(root, repo_binary),
        },
        "packagedCandidates": [
            {
                "path": str(candidate),
                "exists": candidate.is_file(),
                "usable": is_usable_binary(candidate),
            }
            for candidate in packaged_candidates
        ],
        "pathBinary": {
            "path": str(path_binary) if path_binary is not None else None,
            "usable": path_binary is not None and is_usable_binary(path_binary),
        },
        "repoLauncherScript": {
            "path": str(run_tui_script),
            "exists": run_tui_script.is_file(),
        },
    }


def render_install_info(payload: dict[str, Any]) -> str:
    lines = [
        f"poor-cli {payload['version']}",
        f"Platform: {payload['platform']} ({payload['machine']})",
        f"TUI executable: {payload['tuiExecutableName']}",
    ]

    selected = payload.get("selectedLauncher")
    if isinstance(selected, dict):
        lines.append(f"Resolved launcher: {selected['source']} -> {selected['path']}")
    else:
        lines.append("Resolved launcher: not found")

    env_override = payload["envOverride"]
    if env_override["configured"]:
        status = "usable" if env_override["usable"] else "missing or not executable"
        lines.append(f"POOR_CLI_TUI_BIN: {env_override['path']} [{status}]")
    else:
        lines.append("POOR_CLI_TUI_BIN: not set")

    repo_binary = payload["repoBinary"]
    repo_status = "fresh" if repo_binary["fresh"] else "missing or stale"
    lines.append(f"Repo release binary: {repo_binary['path']} [{repo_status}]")

    path_binary = payload["pathBinary"]
    if path_binary["path"]:
        lines.append(f"PATH binary: {path_binary['path']}")
    else:
        lines.append("PATH binary: not found")

    repo_script = payload["repoLauncherScript"]
    lines.append(
        "Repo launcher script: "
        f"{repo_script['path']} [{'available' if repo_script['exists'] else 'missing'}]"
    )

    packaged_candidates = payload["packagedCandidates"]
    if packaged_candidates:
        lines.append("Packaged TUI candidates:")
        for candidate in packaged_candidates:
            status = "usable" if candidate["usable"] else "missing"
            lines.append(f"  {candidate['path']} [{status}]")

    lines.append("Tip: set POOR_CLI_TUI_BIN to force a specific TUI binary.")
    return "\n".join(lines)


def build_install_info_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="poor-cli install-info")
    parser.add_argument("--json", action="store_true")
    return parser


def run_install_info_mode(argv: Sequence[str]) -> int:
    parser = build_install_info_parser()
    args = parser.parse_args(list(argv))
    payload = inspect_tui_installation()
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_install_info(payload))
    return 0


def launch_tui(argv: list[str]) -> int:
    if run_tui_binary(argv) == 0:
        return 0
    if run_tui_from_repo(argv) == 0:
        return 0
    raise SystemExit(
        "Rust TUI launcher not found.\n\n"
        "Interactive options:\n"
        "  - Run ./run_tui.sh from a repo checkout\n"
        "  - Install or place a `poor-cli-tui` binary in PATH\n"
        "  - Set POOR_CLI_TUI_BIN=/path/to/poor-cli-tui\n"
        "  - Run `poor-cli install-info` to inspect launcher paths\n\n"
        "Python surfaces still available:\n"
        "  - `poor-cli exec --help`\n"
        "  - `poor-cli task --help`\n"
        "  - `poor-cli automation --help`\n"
        "  - `poor-cli skills --help`\n"
        "  - `poor-cli commands --help`\n"
        "  - `poor-cli server --help`\n\n"
        "Run `poor-cli help` for a full overview."
    )
