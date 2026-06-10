"""Tests for forward-only migrations of persisted-state artifacts (PRD 003)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from poor_cli.persisted import (
    CURRENT_VERSIONS,
    ForwardMigrationFailed,
    load_json,
)
from poor_cli.persisted.migrations import MIGRATIONS, migrate_forward
from poor_cli.persisted.schema import LEGACY_BACKUP_DIRNAME

FIXTURES = Path(__file__).parent / "fixtures" / "persisted"


def test_v0_preferences_auto_upgrade(tmp_path: Path) -> None:
    target = tmp_path / "preferences.json"
    shutil.copy(FIXTURES / "preferences_v0.json", target)

    original_payload = json.loads(target.read_text(encoding="utf-8"))
    # Sanity: fixture is truly pre-envelope.
    assert "schema_version" not in original_payload

    loaded = load_json(target, "preferences")
    assert loaded == original_payload

    on_disk = json.loads(target.read_text(encoding="utf-8"))
    assert on_disk == {
        "schema_version": CURRENT_VERSIONS["preferences"],
        "artifact": "preferences",
        "data": original_payload,
    }


def test_legacy_v0_backup_created(tmp_path: Path) -> None:
    target = tmp_path / "preferences.json"
    shutil.copy(FIXTURES / "preferences_v0.json", target)
    expected_content = target.read_bytes()

    load_json(target, "preferences")

    backup_dir = tmp_path / LEGACY_BACKUP_DIRNAME
    assert backup_dir.is_dir()
    backups = list(backup_dir.glob("preferences.json.*.bak"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == expected_content


def test_reload_after_upgrade_does_not_create_second_backup(tmp_path: Path) -> None:
    target = tmp_path / "preferences.json"
    shutil.copy(FIXTURES / "preferences_v0.json", target)

    load_json(target, "preferences")
    load_json(target, "preferences")  # already an envelope — no backup

    backups = list((tmp_path / LEGACY_BACKUP_DIRNAME).glob("preferences.json.*.bak"))
    assert len(backups) == 1


def test_migrate_forward_chains_migrations_in_order() -> None:
    calls: list[int] = []

    def step(tag: int):
        def _apply(data):
            calls.append(tag)
            return {**data, f"v{tag}": True}

        return _apply

    MIGRATIONS["test_artifact"] = {0: step(1), 1: step(2), 2: step(3)}
    try:
        CURRENT_VERSIONS["test_artifact"] = 3
        result = migrate_forward("test_artifact", {}, from_version=0, to_version=3)
        assert calls == [1, 2, 3]
        assert result == {"v1": True, "v2": True, "v3": True}
    finally:
        del MIGRATIONS["test_artifact"]
        del CURRENT_VERSIONS["test_artifact"]


def test_missing_migration_raises_explicitly() -> None:
    MIGRATIONS["gappy"] = {0: lambda d: d}
    try:
        CURRENT_VERSIONS["gappy"] = 3
        with pytest.raises(ForwardMigrationFailed):
            migrate_forward("gappy", {}, from_version=0, to_version=3)
    finally:
        del MIGRATIONS["gappy"]
        del CURRENT_VERSIONS["gappy"]


def test_migrate_forward_identity_when_versions_match() -> None:
    payload = {"x": 1}
    assert migrate_forward("preferences", payload, from_version=1, to_version=1) is payload


def test_migrate_forward_rejects_backwards() -> None:
    with pytest.raises(ForwardMigrationFailed):
        migrate_forward("preferences", {}, from_version=2, to_version=1)
