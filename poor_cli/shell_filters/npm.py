from __future__ import annotations

from . import register

_KEEP_PREFIXES = ("npm ERR!", "npm WARN")
_KEEP_SUBSTRINGS = (
    "added ",
    "removed ",
    "changed ",
    "audited ",
    "packages are looking for funding",
    "vulnerabilities",
    "up to date",
)


@register(("npm", "install"))
def filter_npm_install(output: str) -> str:
    kept = [line.strip() for line in output.splitlines() if _keep_line(line)]
    if not kept:
        return output
    return "\n".join(["npm install", *kept])


def _keep_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    return stripped.startswith(_KEEP_PREFIXES) or any(item in stripped for item in _KEEP_SUBSTRINGS)
