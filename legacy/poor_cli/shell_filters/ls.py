from __future__ import annotations

from . import register


@register(("ls", "-la"))
@register(("ls", "-al"))
def filter_ls_la(output: str) -> str:
    lines = output.splitlines()
    entries: list[str] = []
    total = ""
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("total "):
            total = stripped
            continue
        parts = stripped.split(maxsplit=8)
        if len(parts) < 9 or not parts[0]:
            entries.append(stripped)
            continue
        type_name = _entry_type(parts[0][0])
        size = parts[4]
        name = parts[8]
        entries.append(f"{type_name} {size} {name}")
    if not entries:
        return output
    header = f"ls -la: {len(entries)} entries"
    if total:
        header += f", {total}"
    return "\n".join([header, *entries])


def _entry_type(mode: str) -> str:
    if mode == "d":
        return "dir"
    if mode == "l":
        return "link"
    if mode == "-":
        return "file"
    return mode or "entry"
