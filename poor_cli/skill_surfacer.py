"""Auto-surface relevant skills based on user prompt intent."""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence

_INTENT_KEYWORDS: Dict[str, List[str]] = { # skill name -> trigger keywords
    "commit": ["commit", "git commit", "stage", "push"],
    "review": ["review", "code review", "pr review", "pull request review"],
    "test": ["test", "unit test", "integration test", "run tests", "pytest", "jest"],
    "deploy": ["deploy", "release", "publish", "ship"],
    "refactor": ["refactor", "clean up", "simplify", "restructure"],
    "docs": ["document", "docstring", "readme", "documentation", "jsdoc"],
    "debug": ["debug", "breakpoint", "trace", "stacktrace", "error", "bug"],
    "migrate": ["migrate", "migration", "upgrade", "database migration"],
    "scaffold": ["scaffold", "boilerplate", "template", "init", "bootstrap"],
    "lint": ["lint", "format", "prettier", "eslint", "ruff", "black"],
}
_KEYWORD_PATTERNS: Dict[str, re.Pattern] = {
    name: re.compile(r"\b(?:" + "|".join(re.escape(kw) for kw in kws) + r")\b", re.I)
    for name, kws in _INTENT_KEYWORDS.items()
}


def detect_relevant_skills(
    user_prompt: str,
    available_skill_names: Sequence[str],
    max_hints: int = 3,
) -> List[str]:
    """Return skill names relevant to the user prompt, capped at max_hints."""
    if not user_prompt or not available_skill_names:
        return []
    available = set(available_skill_names)
    scored: List[tuple] = []
    for name, pattern in _KEYWORD_PATTERNS.items():
        if name not in available:
            continue
        matches = pattern.findall(user_prompt)
        if matches:
            scored.append((len(matches), name))
    scored.sort(reverse=True)
    return [name for _, name in scored[:max_hints]]


def build_skill_hints(
    skill_names: Sequence[str],
    skill_descriptions: Optional[Dict[str, str]] = None,
) -> str:
    """Build a compact skill hint block for injection into the system message."""
    if not skill_names:
        return ""
    descs = skill_descriptions or {}
    lines = ["Available skills (invoke via /skill_name):"]
    for name in skill_names:
        desc = descs.get(name, "")
        line = f"- /{name}" + (f": {desc}" if desc else "")
        lines.append(line)
    return "\n".join(lines)
