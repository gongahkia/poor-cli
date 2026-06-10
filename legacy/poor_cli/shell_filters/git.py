from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import register

_STATUS_SECTION_HEADERS = {
    "Changes to be committed:": "staged",
    "Changes not staged for commit:": "unstaged",
    "Untracked files:": "untracked",
    "Unmerged paths:": "unmerged",
}
_STATUS_ITEM_RE = re.compile(r"^\s+(modified|new file|deleted|renamed|copied|typechange|both modified|both added|both deleted):\s+(.+)$")
_STAT_RE = re.compile(r"^(?P<path>.+?)\s+\|\s+(?P<count>\d+|-)\s*(?P<graph>[+\-]+)?\s*$")


@dataclass
class _GitStatus:
    branch: str = ""
    tracking: list[str] = field(default_factory=list)
    sections: dict[str, list[tuple[str, str]]] = field(default_factory=lambda: {
        "staged": [],
        "unstaged": [],
        "untracked": [],
        "unmerged": [],
        "other": [],
    })


@register(("git", "status"))
def filter_git_status(output: str) -> str:
    if _looks_porcelain(output):
        return _filter_porcelain_status(output)
    status = _GitStatus()
    section = "other"
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("On branch "):
            status.branch = stripped.removeprefix("On branch ").strip()
            continue
        if stripped.startswith("Your branch "):
            status.tracking.append(stripped.rstrip("."))
            continue
        if stripped in _STATUS_SECTION_HEADERS:
            section = _STATUS_SECTION_HEADERS[stripped]
            continue
        if stripped.startswith("(") or stripped.startswith("use "):
            continue
        match = _STATUS_ITEM_RE.match(line)
        if match:
            status.sections.setdefault(section, []).append((_status_code(match.group(1)), match.group(2).strip()))
            continue
        if section == "untracked" and not stripped.startswith(("no changes", "nothing to commit")):
            status.sections["untracked"].append(("??", stripped))
    headline = "status"
    if status.branch:
        headline += f" {status.branch}"
    for item in status.tracking:
        headline += f" {_compact_tracking(item)}"
    lines: list[str] = [headline]
    for name, marker in (("staged", "S"), ("unstaged", "W"), ("untracked", "?"), ("unmerged", "X")):
        items = status.sections.get(name, [])
        if not items:
            continue
        lines.append(f"{marker}{len(items)}: " + ",".join(path for _, path in items))
    if len(lines) == 1:
        return output
    return "\n".join(lines)


@register(("git", "diff", "--stat"))
def filter_git_diff_stat(output: str) -> str:
    rows: list[str] = []
    summary = ""
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if " changed" in stripped or " insertion" in stripped or " deletion" in stripped:
            summary = stripped
            continue
        match = _STAT_RE.match(stripped)
        if not match:
            rows.append(stripped)
            continue
        graph = match.group("graph") or ""
        plus = graph.count("+")
        minus = graph.count("-")
        count = match.group("count")
        suffix = f"+{plus} -{minus}" if graph else f"{count} changes"
        rows.append(f"{match.group('path').strip()} {suffix}")
    if not rows:
        return output
    lines = ["git diff --stat", *rows]
    if summary:
        lines.append(summary)
    return "\n".join(lines)


def _looks_porcelain(output: str) -> bool:
    for line in output.splitlines():
        if line.startswith("## ") or line.startswith((" M ", "M  ", "A  ", "D  ", "?? ", "R  ", "C  ", "UU ")):
            return True
    return False


def _filter_porcelain_status(output: str) -> str:
    rows: list[str] = ["git status"]
    counts: dict[str, int] = {}
    for line in output.splitlines():
        if line.startswith("## "):
            rows.append(f"branch: {line[3:].strip()}")
            continue
        if len(line) < 4:
            continue
        code = line[:2]
        path = line[3:].strip()
        if not path:
            continue
        kind = _porcelain_kind(code)
        counts[kind] = counts.get(kind, 0) + 1
        rows.append(f"{kind}: {path}")
    if len(rows) == 1:
        return output
    summary = ", ".join(f"{key}={value}" for key, value in sorted(counts.items()))
    if summary:
        rows.insert(1, f"counts: {summary}")
    return "\n".join(rows)


def _porcelain_kind(code: str) -> str:
    if code == "??":
        return "untracked"
    if "U" in code:
        return "unmerged"
    if code[0] != " ":
        return "staged"
    return "unstaged"


def _status_code(kind: str) -> str:
    return {
        "modified": "M",
        "new file": "A",
        "deleted": "D",
        "renamed": "R",
        "copied": "C",
        "typechange": "T",
        "both modified": "UU",
        "both added": "AA",
        "both deleted": "DD",
    }.get(kind, kind)


def _compact_tracking(line: str) -> str:
    match = re.search(r"ahead of '([^']+)' by (\d+) commit", line)
    if match:
        return f"+{match.group(2)}"
    match = re.search(r"behind '([^']+)' by (\d+) commit", line)
    if match:
        return f"-{match.group(2)}"
    return line
