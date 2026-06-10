"""PRD 064 one-shot migration into AutomationRule storage."""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .rules import (
    AutomationRule,
    automation_rule_from_dict,
    rule_from_automation_payload,
    rule_from_custom_command,
    rule_from_workflow_template,
)


BACKUP_DIR_NAME = "backup-pre-064"
RULES_VERSION = 1


@dataclass(frozen=True)
class MigrationResult:
    migrated: bool
    dry_run: bool
    backup_dir: str
    output_path: str
    rule_count: int
    backed_up: List[str]
    skipped_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "migrated": self.migrated,
            "dryRun": self.dry_run,
            "backupDir": self.backup_dir,
            "outputPath": self.output_path,
            "ruleCount": self.rule_count,
            "backedUp": list(self.backed_up),
            "skippedReason": self.skipped_reason,
        }


def migrate_extensions(
    repo_root: Optional[Path] = None,
    *,
    dry_run: bool = False,
    force: bool = False,
) -> MigrationResult:
    root = (repo_root or Path.cwd()).resolve()
    state_dir = root / ".poor-cli"
    backup_dir = state_dir / BACKUP_DIR_NAME
    output_path = state_dir / "automations.json"

    if backup_dir.exists() and not force:
        existing_rules = _read_existing_rules(output_path)
        return MigrationResult(
            migrated=False,
            dry_run=dry_run,
            backup_dir=str(backup_dir),
            output_path=str(output_path),
            rule_count=len(existing_rules),
            backed_up=[],
            skipped_reason="backup-exists",
        )

    rules = _collect_rules(state_dir)
    backup_targets = list(_backup_targets(state_dir))
    if dry_run:
        return MigrationResult(
            migrated=False,
            dry_run=True,
            backup_dir=str(backup_dir),
            output_path=str(output_path),
            rule_count=len(rules),
            backed_up=[str(path) for path in backup_targets],
            skipped_reason="dry-run",
        )

    state_dir.mkdir(parents=True, exist_ok=True)
    backup_dir.mkdir(parents=True, exist_ok=True)
    backed_up = _write_backups(state_dir, backup_dir, backup_targets)
    _write_rules(output_path, rules)
    _write_manifest(backup_dir, backed_up)
    return MigrationResult(
        migrated=True,
        dry_run=False,
        backup_dir=str(backup_dir),
        output_path=str(output_path),
        rule_count=len(rules),
        backed_up=[str(path) for path in backed_up],
    )


def restore_migration(repo_root: Optional[Path] = None, *, dry_run: bool = False) -> MigrationResult:
    root = (repo_root or Path.cwd()).resolve()
    state_dir = root / ".poor-cli"
    backup_dir = state_dir / BACKUP_DIR_NAME
    output_path = state_dir / "automations.json"
    if not backup_dir.exists():
        return MigrationResult(
            migrated=False,
            dry_run=dry_run,
            backup_dir=str(backup_dir),
            output_path=str(output_path),
            rule_count=0,
            backed_up=[],
            skipped_reason="missing-backup",
        )

    manifest = _load_json_file(backup_dir / "manifest.json")
    targets = manifest.get("backedUp") if isinstance(manifest, dict) else []
    restored: List[Path] = []
    for raw_target in targets if isinstance(targets, list) else []:
        target = state_dir / str(raw_target)
        source = backup_dir / str(raw_target)
        if source.exists():
            restored.append(target)
            if not dry_run:
                target.parent.mkdir(parents=True, exist_ok=True)
                if source.is_dir():
                    if target.exists():
                        shutil.rmtree(target)
                    shutil.copytree(source, target)
                else:
                    shutil.copy2(source, target)
    if "automations.json" not in set(str(item) for item in targets if isinstance(targets, list)) and output_path.exists() and not dry_run:
        output_path.unlink()
    return MigrationResult(
        migrated=bool(restored) and not dry_run,
        dry_run=dry_run,
        backup_dir=str(backup_dir),
        output_path=str(output_path),
        rule_count=0,
        backed_up=[str(path) for path in restored],
        skipped_reason="dry-run" if dry_run else "",
    )


def _collect_rules(state_dir: Path) -> List[AutomationRule]:
    rules: List[AutomationRule] = []
    seen: set[str] = set()
    for rule in [
        *_rules_from_custom_commands_json(state_dir / "custom_commands.json"),
        *_rules_from_command_dir(state_dir / "commands", scope="repo"),
        *_rules_from_workflow_templates_json(state_dir / "workflow_templates.json"),
        *_rules_from_automations_json(state_dir / "automations.json"),
        *_rules_from_automation_db(state_dir / "tasks" / "automations.db"),
    ]:
        if rule.id in seen:
            continue
        seen.add(rule.id)
        rules.append(rule)
    return rules


def _rules_from_custom_commands_json(path: Path) -> List[AutomationRule]:
    return [rule_from_custom_command(item) for item in _iter_records(_load_json_file(path), "commands")]


def _rules_from_command_dir(path: Path, *, scope: str) -> List[AutomationRule]:
    if not path.is_dir():
        return []
    rules: List[AutomationRule] = []
    for command_file in sorted(path.glob("*.md")):
        body = command_file.read_text(encoding="utf-8")
        rules.append(
            rule_from_custom_command(
                {
                    "name": command_file.stem,
                    "path": str(command_file),
                    "description": _description_from_markdown(body),
                    "scope": scope,
                    "template": body,
                }
            )
        )
    return rules


def _rules_from_workflow_templates_json(path: Path) -> List[AutomationRule]:
    return [rule_from_workflow_template(item) for item in _iter_records(_load_json_file(path), "workflows")]


def _rules_from_automations_json(path: Path) -> List[AutomationRule]:
    data = _load_json_file(path)
    records = [] if isinstance(data, dict) and isinstance(data.get("rules"), list) else list(_iter_records(data, "automations"))
    if isinstance(data, dict):
        records.extend(item for item in data.get("rules", []) if isinstance(item, dict))
    rules: List[AutomationRule] = []
    for item in records:
        if isinstance(item.get("triggers"), list) and isinstance(item.get("steps"), list):
            rules.append(automation_rule_from_dict(item))
        else:
            rules.append(rule_from_automation_payload(item))
    return rules


def _rules_from_automation_db(path: Path) -> List[AutomationRule]:
    if not path.exists():
        return []
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute("SELECT * FROM automations").fetchall()
    except sqlite3.Error:
        return []
    finally:
        connection.close()
    rules: List[AutomationRule] = []
    for row in rows:
        schedule = _loads_json(str(row["schedule_json"] or "{}"))
        metadata = _loads_json(str(row["metadata_json"] or "{}"))
        rules.append(
            rule_from_automation_payload(
                {
                    "automationId": row["automation_id"],
                    "name": row["name"],
                    "prompt": row["prompt"],
                    "schedule": schedule if isinstance(schedule, dict) else {},
                    "enabled": bool(row["enabled"]),
                    "metadata": metadata if isinstance(metadata, dict) else {},
                }
            )
        )
    return rules


def _read_existing_rules(path: Path) -> List[AutomationRule]:
    if not path.exists():
        return []
    data = _load_json_file(path)
    return [
        automation_rule_from_dict(item)
        for item in (data.get("rules", []) if isinstance(data, dict) else [])
        if isinstance(item, dict)
    ]


def _backup_targets(state_dir: Path) -> Iterable[Path]:
    for relative in (
        "custom_commands.json",
        "workflow_templates.json",
        "automations.json",
        "commands",
        "tasks/automations.db",
    ):
        target = state_dir / relative
        if target.exists():
            yield target


def _write_backups(state_dir: Path, backup_dir: Path, targets: Iterable[Path]) -> List[Path]:
    backed_up: List[Path] = []
    for source in targets:
        relative = source.relative_to(state_dir)
        destination = backup_dir / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            if destination.exists():
                shutil.rmtree(destination)
            shutil.copytree(source, destination)
        else:
            shutil.copy2(source, destination)
        backed_up.append(relative)
    return backed_up


def _write_rules(path: Path, rules: List[AutomationRule]) -> None:
    payload = {
        "version": RULES_VERSION,
        "rules": [rule.to_dict() for rule in rules],
        "legacyAliases": {
            "commands": True,
            "workflow": True,
            "automation": True,
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_manifest(backup_dir: Path, backed_up: List[Path]) -> None:
    payload = {"version": RULES_VERSION, "backedUp": [str(path) for path in backed_up]}
    (backup_dir / "manifest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _iter_records(data: Any, key: str) -> Iterable[Dict[str, Any]]:
    if isinstance(data, list):
        yield from (item for item in data if isinstance(item, dict))
    elif isinstance(data, dict):
        values = data.get(key)
        if isinstance(values, list):
            yield from (item for item in values if isinstance(item, dict))
        elif key in data:
            return
        else:
            for name, value in data.items():
                if isinstance(value, dict):
                    yield {"name": name, **value}


def _load_json_file(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _loads_json(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def _description_from_markdown(body: str) -> str:
    for line in (line.strip() for line in body.splitlines()):
        if line and not line.startswith("#"):
            return line
    return "No description provided."


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m poor_cli.automations.migration")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--restore", action="store_true")
    args = parser.parse_args()
    result = restore_migration(args.repo_root, dry_run=args.dry_run) if args.restore else migrate_extensions(
        args.repo_root,
        dry_run=args.dry_run,
        force=args.force,
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
