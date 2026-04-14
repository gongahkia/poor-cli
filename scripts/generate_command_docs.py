#!/usr/bin/env python3
"""Generate docs/COMMANDS.md from poor_cli/command_manifest.json.

Run before each release; the resulting file is the authoritative reference for
all 120+ slash commands. Keeping it generated keeps the doc in lockstep with
the manifest so users never see stale entries.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "poor_cli" / "command_manifest.json"
OUT = ROOT / "docs" / "COMMANDS.md"


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    commands = manifest.get("commands", [])
    by_cat: dict[str, list[dict]] = defaultdict(list)
    for c in commands:
        by_cat[c.get("category", "Misc")].append(c)

    lines = [
        "# Slash Command Reference",
        "",
        f"poor-cli ships **{len(commands)} slash commands** across {len(by_cat)} categories.",
        "Generated from `poor_cli/command_manifest.json` — do not edit by hand.",
        "Re-run `python scripts/generate_command_docs.py` after manifest changes.",
        "",
        "## Categories",
        "",
    ]
    for cat in sorted(by_cat):
        anchor = cat.lower().replace(" ", "-").replace("&", "")
        lines.append(f"- [{cat}](#{anchor.replace('--', '-')}) ({len(by_cat[cat])} commands)")
    lines.append("")

    for cat in sorted(by_cat):
        lines.append(f"## {cat}")
        lines.append("")
        lines.append("| Command | Description |")
        lines.append("|---|---|")
        for c in sorted(by_cat[cat], key=lambda x: x["command"]):
            cmd = c["command"]
            desc = c.get("description", "").replace("|", "\\|")
            star = " ⭐" if c.get("recommended") else ""
            lines.append(f"| `{cmd}`{star} | {desc} |")
        lines.append("")

    lines.extend([
        "## Conventions",
        "",
        "- ⭐ = recommended starting point for new users.",
        "- Type `/` in chat to trigger the slash autocomplete picker (PRD 045).",
        "- Custom slash commands defined via AutomationRule (`type: slash`) appear here only after manifest regeneration; see `docs/AUTOMATIONS.md`.",
        "",
        "## See also",
        "",
        "- [PROVIDERS.md](./PROVIDERS.md) — `/switch`, `/provider`, `/api-key`",
        "- [ECONOMY.md](./ECONOMY.md) — `/broke`, `/my-treat`, `/economy`, `/savings`",
        "- [SANDBOX.md](./SANDBOX.md) — `/sandbox`, `/permission-mode`, `/trust`, `/policy`",
        "- [AUTOMATIONS.md](./AUTOMATIONS.md) — `/automation`, `/workflow`, `/skills`",
        "- [MULTIPLAYER.md](./MULTIPLAYER.md) — `/collab`, `/pass`, `/suggest`, `/leave`",
        "- [AUTO_COMMIT.md](./AUTO_COMMIT.md) — `/commit`",
        "",
    ])
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({len(commands)} commands)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
