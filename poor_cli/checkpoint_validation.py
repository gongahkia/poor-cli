"""
Checkpoint validation and repair for poor-cli

Validates checkpoint integrity and attempts repairs.
"""

from pathlib import Path
from typing import List, Dict, Any, Optional
import hashlib

from poor_cli.checkpoint import CheckpointManager, Checkpoint, FileSnapshot
from poor_cli.exceptions import FileOperationError, setup_logger

logger = setup_logger(__name__)


class CheckpointValidationError(Exception):
    """Raised when checkpoint validation fails"""
    pass


class CheckpointValidator:
    """Validates and repairs checkpoints"""

    def __init__(self, checkpoint_manager: CheckpointManager):
        self.manager = checkpoint_manager

    def validate_checkpoint(self, checkpoint_id: str) -> Dict[str, Any]:
        """Validate checkpoint integrity

        Args:
            checkpoint_id: ID of checkpoint to validate

        Returns:
            Dict with validation results:
            {
                "valid": bool,
                "issues": List[str],
                "warnings": List[str],
                "corrupted_files": List[str],
                "missing_files": List[str]
            }
        """
        checkpoint = self.manager.get_checkpoint(checkpoint_id)
        if not checkpoint:
            return {
                "valid": False,
                "issues": [f"Checkpoint not found: {checkpoint_id}"],
                "warnings": [],
                "corrupted_files": [],
                "missing_files": []
            }

        issues = []
        warnings = []
        corrupted_files = []
        missing_files = []

        checkpoint_dir = self.manager._get_checkpoint_dir(checkpoint_id)

        # Check if checkpoint directory exists
        if not checkpoint_dir.exists():
            issues.append(f"Checkpoint directory missing: {checkpoint_dir}")
            return {
                "valid": False,
                "issues": issues,
                "warnings": warnings,
                "corrupted_files": corrupted_files,
                "missing_files": missing_files
            }

        # Validate each snapshot
        for snapshot in checkpoint.snapshots:
            snapshot_file = checkpoint_dir / f"{snapshot.content_hash}.snapshot"

            # Check if snapshot file exists
            if not snapshot_file.exists():
                missing_files.append(str(snapshot_file))
                issues.append(
                    f"Missing snapshot for {snapshot.file_path}: {snapshot.content_hash}.snapshot"
                )
                continue

            # Verify file hash
            try:
                with open(snapshot_file, 'rb') as f:
                    content = f.read()

                actual_hash = hashlib.sha256(content).hexdigest()[:16]

                if actual_hash != snapshot.content_hash:
                    corrupted_files.append(snapshot.file_path)
                    issues.append(
                        f"Hash mismatch for {snapshot.file_path}: "
                        f"expected {snapshot.content_hash}, got {actual_hash}"
                    )

                # Verify size
                if len(content) != snapshot.size_bytes:
                    warnings.append(
                        f"Size mismatch for {snapshot.file_path}: "
                        f"expected {snapshot.size_bytes}, got {len(content)}"
                    )

            except Exception as e:
                issues.append(f"Error validating {snapshot.file_path}: {e}")
                corrupted_files.append(snapshot.file_path)

        # Check for orphaned snapshot files
        snapshot_hashes = {s.content_hash for s in checkpoint.snapshots}
        for snapshot_file in checkpoint_dir.glob("*.snapshot"):
            file_hash = snapshot_file.stem
            if file_hash not in snapshot_hashes:
                warnings.append(f"Orphaned snapshot file: {snapshot_file.name}")

        valid = len(issues) == 0

        logger.info(
            f"Validated checkpoint {checkpoint_id}: "
            f"valid={valid}, issues={len(issues)}, warnings={len(warnings)}"
        )

        return {
            "valid": valid,
            "issues": issues,
            "warnings": warnings,
            "corrupted_files": corrupted_files,
            "missing_files": missing_files
        }

    def repair_checkpoint(
        self,
        checkpoint_id: str,
        remove_corrupted: bool = True
    ) -> Dict[str, Any]:
        """Attempt to repair a corrupted checkpoint

        Args:
            checkpoint_id: ID of checkpoint to repair
            remove_corrupted: Whether to remove corrupted snapshots

        Returns:
            Dict with repair results:
            {
                "repaired": bool,
                "actions_taken": List[str],
                "removed_snapshots": List[str],
                "remaining_issues": List[str]
            }
        """
        logger.info(f"Attempting to repair checkpoint {checkpoint_id}")

        validation = self.validate_checkpoint(checkpoint_id)

        if validation["valid"]:
            return {
                "repaired": True,
                "actions_taken": ["Checkpoint already valid"],
                "removed_snapshots": [],
                "remaining_issues": []
            }

        checkpoint = self.manager.get_checkpoint(checkpoint_id)
        checkpoint_dir = self.manager._get_checkpoint_dir(checkpoint_id)

        actions_taken = []
        removed_snapshots = []
        remaining_issues = []

        # Remove corrupted snapshots if requested
        if remove_corrupted and validation["corrupted_files"]:
            valid_snapshots = []

            for snapshot in checkpoint.snapshots:
                if snapshot.file_path not in validation["corrupted_files"]:
                    valid_snapshots.append(snapshot)
                else:
                    removed_snapshots.append(snapshot.file_path)
                    actions_taken.append(f"Removed corrupted snapshot: {snapshot.file_path}")

            # Update checkpoint with valid snapshots only
            checkpoint.snapshots = valid_snapshots
            self.manager._save_index()
            actions_taken.append(f"Updated checkpoint index with {len(valid_snapshots)} valid snapshots")

        # Remove orphaned snapshot files
        snapshot_hashes = {s.content_hash for s in checkpoint.snapshots}
        for snapshot_file in checkpoint_dir.glob("*.snapshot"):
            file_hash = snapshot_file.stem
            if file_hash not in snapshot_hashes:
                try:
                    snapshot_file.unlink()
                    actions_taken.append(f"Removed orphaned file: {snapshot_file.name}")
                except Exception as e:
                    remaining_issues.append(f"Failed to remove {snapshot_file.name}: {e}")

        # Re-validate
        final_validation = self.validate_checkpoint(checkpoint_id)

        repaired = final_validation["valid"]

        if not repaired:
            remaining_issues.extend(final_validation["issues"])

        logger.info(
            f"Repair complete for {checkpoint_id}: "
            f"repaired={repaired}, actions={len(actions_taken)}"
        )

        return {
            "repaired": repaired,
            "actions_taken": actions_taken,
            "removed_snapshots": removed_snapshots,
            "remaining_issues": remaining_issues
        }

    def validate_all_checkpoints(self) -> Dict[str, Any]:
        """Validate all checkpoints

        Returns:
            Dict with overall validation results
        """
        results = {
            "total_checkpoints": len(self.manager.checkpoints),
            "valid_checkpoints": 0,
            "corrupted_checkpoints": 0,
            "checkpoint_details": {}
        }

        for checkpoint in self.manager.checkpoints:
            validation = self.validate_checkpoint(checkpoint.checkpoint_id)

            if validation["valid"]:
                results["valid_checkpoints"] += 1
            else:
                results["corrupted_checkpoints"] += 1

            results["checkpoint_details"][checkpoint.checkpoint_id] = {
                "valid": validation["valid"],
                "issue_count": len(validation["issues"]),
                "warning_count": len(validation["warnings"])
            }

        logger.info(
            f"Validated all checkpoints: "
            f"{results['valid_checkpoints']}/{results['total_checkpoints']} valid"
        )

        return results

    def auto_repair_all(self) -> Dict[str, Any]:
        """Attempt to repair all corrupted checkpoints

        Returns:
            Dict with repair summary
        """
        validation = self.validate_all_checkpoints()

        repaired_count = 0
        failed_count = 0
        details = {}

        for checkpoint_id, info in validation["checkpoint_details"].items():
            if not info["valid"]:
                repair_result = self.repair_checkpoint(checkpoint_id)

                if repair_result["repaired"]:
                    repaired_count += 1
                else:
                    failed_count += 1

                details[checkpoint_id] = repair_result

        logger.info(
            f"Auto-repair complete: "
            f"repaired={repaired_count}, failed={failed_count}"
        )

        return {
            "total_corrupted": validation["corrupted_checkpoints"],
            "repaired": repaired_count,
            "failed": failed_count,
            "details": details
        }
