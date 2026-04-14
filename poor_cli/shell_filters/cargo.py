from __future__ import annotations

from . import register

_KEEP_PREFIXES = ("error", "warning", "Finished", "Compiling", "Checking", "Building")
_KEEP_SUBSTRINGS = ("could not compile", "failed to", "aborting")


@register(("cargo", "build"))
def filter_cargo_build(output: str) -> str:
    kept = [line.strip() for line in output.splitlines() if _keep_line(line)]
    if not kept:
        return output
    return "\n".join(["cargo build", *kept])


def _keep_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    return stripped.startswith(_KEEP_PREFIXES) or any(item in stripped for item in _KEEP_SUBSTRINGS)
