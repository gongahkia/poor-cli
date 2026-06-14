from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .dispatcher import ToolResult


def builtin_tools(root: Path) -> dict[str, Any]:
    root = root.resolve()
    return {
        "read_file": lambda args: _read_file(root, args),
        "write_file": lambda args: _write_file(root, args),
        "edit": lambda args: _edit(root, args),
        "glob": lambda args: _glob(root, args),
        "grep": lambda args: _grep(root, args),
        "shell": lambda args: _shell(root, args),
        "replay_emit": _replay_emit,
    }


def _read_file(root: Path, args: dict[str, Any]) -> ToolResult:
    path = _resolve_path(root, args.get("path"))
    max_bytes = int(args.get("max_bytes") or 200_000)
    data = path.read_bytes()
    truncated = len(data) > max_bytes
    text = data[:max_bytes].decode("utf-8", errors="replace")
    return _result("read_file", True, {"path": _relative(root, path), "content": text, "truncated": truncated, "size": len(data)})


def _write_file(root: Path, args: dict[str, Any]) -> ToolResult:
    path = _resolve_path(root, args.get("path"))
    content = str(args.get("content") or "")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return _result("write_file", True, {"path": _relative(root, path), "bytes": len(content.encode())})


def _edit(root: Path, args: dict[str, Any]) -> ToolResult:
    path = _resolve_path(root, args.get("path"))
    old = str(args.get("old") or "")
    new = str(args.get("new") or "")
    count = int(args.get("count") or 1)
    if not old:
        raise ValueError("edit requires non-empty old text")
    text = path.read_text(encoding="utf-8")
    hits = text.count(old) if count < 0 else min(text.count(old), count)
    if hits == 0:
        raise ValueError("old text not found")
    updated = text.replace(old, new, count if count >= 0 else -1)
    path.write_text(updated, encoding="utf-8")
    return _result("edit", True, {"path": _relative(root, path), "replacements": hits})


def _glob(root: Path, args: dict[str, Any]) -> ToolResult:
    pattern = str(args.get("pattern") or "*")
    max_results = int(args.get("max_results") or 200)
    paths = []
    for path in sorted(root.glob(pattern)):
        resolved = path.resolve()
        if _inside(root, resolved):
            paths.append(_relative(root, resolved))
        if len(paths) >= max_results:
            break
    return _result("glob", True, {"matches": paths, "truncated": len(paths) >= max_results})


def _grep(root: Path, args: dict[str, Any]) -> ToolResult:
    pattern = str(args.get("pattern") or "")
    if not pattern:
        raise ValueError("grep requires pattern")
    file_pattern = str(args.get("glob") or "**/*")
    max_results = int(args.get("max_results") or 200)
    regex = re.compile(pattern)
    matches = []
    for path in sorted(root.glob(file_pattern)):
        if not path.is_file() or not _inside(root, path.resolve()):
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for lineno, line in enumerate(lines, 1):
            if regex.search(line):
                matches.append({"path": _relative(root, path.resolve()), "line": lineno, "text": line})
                if len(matches) >= max_results:
                    return _result("grep", True, {"matches": matches, "truncated": True})
    return _result("grep", True, {"matches": matches, "truncated": False})


def _shell(root: Path, args: dict[str, Any]) -> ToolResult:
    command = str(args.get("command") or "")
    timeout = int(args.get("timeout") or 30)
    if not command:
        raise ValueError("shell requires command")
    result = subprocess.run(command, cwd=root, shell=True, text=True, capture_output=True, timeout=timeout, check=False)
    return _result(
        "shell",
        result.returncode == 0,
        {"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr},
        None if result.returncode == 0 else f"command failed: {result.returncode}",
    )


def _replay_emit(args: dict[str, Any]) -> ToolResult:
    return _result("replay_emit", True, {"value": args.get("value"), "args": args})


def _resolve_path(root: Path, value: Any) -> Path:
    if value is None:
        raise ValueError("path is required")
    path = Path(str(value)).expanduser()
    resolved = path.resolve() if path.is_absolute() else (root / path).resolve()
    if not _inside(root, resolved):
        raise ValueError("path outside workdir")
    return resolved


def _inside(root: Path, path: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _relative(root: Path, path: Path) -> str:
    return str(path.relative_to(root))


def _result(name: str, ok: bool, output: Any = None, error: str | None = None) -> ToolResult:
    from .dispatcher import ToolResult

    return ToolResult(name=name, ok=ok, output=output, error=error)
