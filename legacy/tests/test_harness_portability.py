"""Regression test for MH6 harness portability.

Guarantees that no provider adapter binds a session to server-side state that
cannot be reconstructed from ~/.poor-cli/ alone. Protects the open-harness
thesis: if you can't recover from local files, that state is locked in.

Anti-patterns searched:
- OpenAI Responses API stateful flags (``store=True``, ``previous_response_id``).
- Anthropic Managed Agents session IDs.
- Assistants API thread / assistant references.
- Codex-style encrypted compaction references.

Exceptions must be declared via ``poor_cli.providers.portability.enforce_portability``
(which is itself the opt-in gate). Anything else fails the test.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from poor_cli.providers.portability import STATEFUL_FEATURES

PROVIDERS_DIR = Path(__file__).resolve().parent.parent / "poor_cli" / "providers"

# (pattern, feature_code) — each pattern, if found, must appear inside a call
# site guarded by enforce_portability(..., feature=<code>, ...).
STATEFUL_PATTERNS = [
    (re.compile(r"\bstore\s*=\s*True\b"), "openai_responses_stateful"),
    (re.compile(r"\bprevious_response_id\s*="), "openai_responses_stateful"),
    (re.compile(r"\bmanaged_agent\b"), "anthropic_managed_agents"),
    (re.compile(r"\bstore_session\s*="), "provider_side_memory"),
    (re.compile(r"\bassistant_id\s*="), "provider_side_memory"),
    (re.compile(r"\bthread_id\s*="), "provider_side_memory"),
]


def _provider_files() -> list[Path]:
    """Return every provider adapter (excluding base + portability utility)."""
    return sorted(
        p for p in PROVIDERS_DIR.glob("*_provider.py")
        if p.name not in {"__init__.py", "portability.py", "capability.py"}
    )


def _strip_comments_and_docstrings(src: str) -> str:
    """Return src with docstrings and inline comments replaced by blanks.

    Preserves line numbers so violation messages stay accurate.
    Only code — not documentation text mentioning the forbidden pattern —
    should trip the portability gate.
    """
    import re as _re
    # strip triple-quoted strings (both flavors) — greedy across lines
    def _blank_match(m):
        return "\n" * m.group(0).count("\n")
    without_triple = _re.sub(r'"""[\s\S]*?"""', _blank_match, src)
    without_triple = _re.sub(r"'''[\s\S]*?'''", _blank_match, without_triple)
    # strip line comments (# ...)
    lines = without_triple.splitlines(keepends=True)
    stripped = []
    for line in lines:
        idx = line.find("#")
        if idx >= 0:
            # keep prefix before # + newline
            stripped.append(line[:idx] + ("\n" if line.endswith("\n") else ""))
        else:
            stripped.append(line)
    return "".join(stripped)


class HarnessPortabilityTests(unittest.TestCase):
    def test_no_stateful_pattern_without_enforce_guard(self):
        violations: list[str] = []
        for path in _provider_files():
            src_full = path.read_text(encoding="utf-8")
            src = _strip_comments_and_docstrings(src_full)
            has_enforce = "enforce_portability(" in src
            for pattern, code in STATEFUL_PATTERNS:
                for match in pattern.finditer(src):
                    # locate the enclosing function — pattern must be within a
                    # block that calls enforce_portability with this code.
                    # coarse check: the feature code appears somewhere in file
                    feature_guarded = code in src and has_enforce
                    if not feature_guarded:
                        line_no = src.count("\n", 0, match.start()) + 1
                        violations.append(f"{path.name}:{line_no}: uses {pattern.pattern!r} without enforce_portability guard for '{code}'")
        self.assertEqual(violations, [], "Stateful-API pattern without portability guard:\n" + "\n".join(violations))

    def test_portability_feature_catalog_is_non_empty(self):
        # defensive: if someone empties STATEFUL_FEATURES the enforcement
        # catalog still needs documented entries.
        self.assertGreaterEqual(len(STATEFUL_FEATURES), 4)
        for code, description in STATEFUL_FEATURES.items():
            self.assertIsInstance(code, str)
            self.assertTrue(description.strip(), f"{code} has empty description")

    def test_provider_adapters_do_not_store_session_ids(self):
        # any attribute assignment like `self._server_session_id = ...` or
        # `self.remote_state = ...` is suspect. We allow `session_id` as a
        # parameter name or local variable, but not as a persistent attribute.
        bad = re.compile(r"\bself\.(?:_?remote_session|_?server_session|_stateful)\b")
        violations = []
        for path in _provider_files():
            src = path.read_text(encoding="utf-8")
            for match in bad.finditer(src):
                line_no = src.count("\n", 0, match.start()) + 1
                violations.append(f"{path.name}:{line_no}: persistent server-session attribute")
        self.assertEqual(violations, [], "Provider stores persistent server-session state:\n" + "\n".join(violations))


if __name__ == "__main__":
    unittest.main()
