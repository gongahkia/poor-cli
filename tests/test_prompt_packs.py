from __future__ import annotations

import json
from pathlib import Path

import pytest

from poor_cli.cli import main
from poor_cli.config import empty_config
from poor_cli.prompt_packs import PromptPackError, prompt_efficiency_report, prompt_prefix, validate_prompt_pack_payload


def test_builtin_prompt_pack_selection_and_cli(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)

    assert "critical" in prompt_prefix(empty_config(), "reviewer", tmp_path).lower()
    assert main(["prompt", "packs", "--json"]) == 0
    packs = json.loads(capsys.readouterr().out)["packs"]
    ids = {pack["id"] for pack in packs}

    assert {"planner.default", "executor.native", "reviewer.anti_sycophancy", "graph.navigator"} <= ids


def test_prompt_pack_provenance_is_required() -> None:
    with pytest.raises(PromptPackError, match="missing fields"):
        validate_prompt_pack_payload({"id": "bad", "template": "copy"})
    with pytest.raises(PromptPackError, match="disallowed provenance"):
        validate_prompt_pack_payload(
            {
                "id": "bad",
                "version": "1",
                "license": "unknown",
                "source_url": "https://example.test",
                "scope": "review",
                "roles": ["reviewer"],
                "template": "copied prompt",
                "arguments": [],
                "provenance_status": "copied-external",
            }
        )


def test_prompt_efficiency_report_counts_delta() -> None:
    report = prompt_efficiency_report("short", "shorter prompt")

    assert report["schema_version"] == "poor-cli-prompt-efficiency-v1"
    assert report["delta_bytes"] == len("shorter prompt") - len("short")
