"""
Checkpoint Integration Tools for poor-cli

Integrations with external systems:
- Export checkpoints as git commits
- Import/export checkpoint archives (local tar.gz)
"""

import subprocess
import json
import tarfile
import tempfile
from pathlib import Path
from typing import List, Optional
import shutil

from poor_cli.checkpoint import Checkpoint, CheckpointManager, FileSnapshot
from poor_cli.exceptions import FileOperationError, setup_logger

logger = setup_logger(__name__)


class GitIntegration:
    """Export checkpoints as git commits"""

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self._check_git_available()

    def _check_git_available(self):
        """Check if git is available"""
        try:
            subprocess.run(
                ["git", "--version"],
                capture_output=True,
                check=True
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.warning("Git not available - git integration disabled")

    def is_git_repo(self) -> bool:
        """Check if workspace is a git repository"""
        git_dir = self.workspace_root / ".git"
        return git_dir.exists() and git_dir.is_dir()

    def export_checkpoint_as_commit(
        self,
        checkpoint: Checkpoint,
        branch_name: Optional[str] = None,
        create_branch: bool = True
    ) -> Optional[str]:
        """Export checkpoint as a git commit

        Args:
            checkpoint: Checkpoint to export
            branch_name: Branch name (default: checkpoint_<id>)
            create_branch: Create new branch for commit

        Returns:
            Commit SHA if successful, None otherwise
        """
        if not self.is_git_repo():
            logger.error("Not a git repository")
            return None

        # Default branch name
        if not branch_name:
            branch_name = f"checkpoint_{checkpoint.checkpoint_id[:8]}"

        try:
            # Save current branch
            current_branch = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=self.workspace_root,
                capture_output=True,
                text=True,
                check=True
            ).stdout.strip()

            # Create and checkout new branch if requested
            if create_branch:
                subprocess.run(
                    ["git", "checkout", "-b", branch_name],
                    cwd=self.workspace_root,
                    capture_output=True,
                    check=True
                )
                logger.info(f"Created branch: {branch_name}")

            # Stage checkpoint files
            for snapshot in checkpoint.snapshots:
                file_path = Path(snapshot.file_path)
                if file_path.exists():
                    subprocess.run(
                        ["git", "add", str(file_path)],
                        cwd=self.workspace_root,
                        capture_output=True,
                        check=True
                    )

            # Create commit message
            commit_message = self._build_commit_message(checkpoint)

            # Commit
            result = subprocess.run(
                ["git", "commit", "-m", commit_message],
                cwd=self.workspace_root,
                capture_output=True,
                text=True,
                check=True
            )

            # Get commit SHA
            commit_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.workspace_root,
                capture_output=True,
                text=True,
                check=True
            ).stdout.strip()

            logger.info(f"Created commit: {commit_sha}")

            # Return to original branch if we created a new one
            if create_branch:
                subprocess.run(
                    ["git", "checkout", current_branch],
                    cwd=self.workspace_root,
                    capture_output=True,
                    check=True
                )

            return commit_sha

        except subprocess.CalledProcessError as e:
            logger.error(f"Git operation failed: {e}")
            # Try to return to original branch
            try:
                if create_branch and 'current_branch' in locals():
                    subprocess.run(
                        ["git", "checkout", current_branch],
                        cwd=self.workspace_root,
                        capture_output=True
                    )
            except (subprocess.SubprocessError, OSError):
                pass
            return None

    def _build_commit_message(self, checkpoint: Checkpoint) -> str:
        """Build git commit message from checkpoint"""
        lines = [
            f"checkpoint: {checkpoint.description}",
            "",
            f"Checkpoint ID: {checkpoint.checkpoint_id}",
            f"Created: {checkpoint.created_at}",
            f"Type: {checkpoint.operation_type}",
            f"Files: {checkpoint.get_file_count()}",
        ]

        if checkpoint.tags:
            lines.append(f"Tags: {', '.join(checkpoint.tags)}")

        if checkpoint.metadata:
            lines.append("")
            lines.append("Metadata:")
            for key, value in checkpoint.metadata.items():
                lines.append(f"  {key}: {value}")

        return "\n".join(lines)

    def import_commit_as_checkpoint(
        self,
        commit_sha: str,
        checkpoint_manager: CheckpointManager
    ) -> Optional[Checkpoint]:
        """Import a git commit as a checkpoint

        Args:
            commit_sha: Git commit SHA
            checkpoint_manager: CheckpointManager instance

        Returns:
            Created checkpoint or None
        """
        if not self.is_git_repo():
            logger.error("Not a git repository")
            return None

        try:
            # Get commit info
            commit_info = subprocess.run(
                ["git", "show", "--name-only", "--pretty=format:%s%n%b", commit_sha],
                cwd=self.workspace_root,
                capture_output=True,
                text=True,
                check=True
            ).stdout

            lines = commit_info.split("\n")
            description = lines[0] if lines else f"Import from commit {commit_sha[:8]}"

            # Get list of files in commit
            file_list = subprocess.run(
                ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", commit_sha],
                cwd=self.workspace_root,
                capture_output=True,
                text=True,
                check=True
            ).stdout.strip().split("\n")

            file_paths = [str(self.workspace_root / f) for f in file_list if f]

            # Create checkpoint
            checkpoint = checkpoint_manager.create_checkpoint(
                file_paths=file_paths,
                description=description,
                operation_type="git_import",
                tags=["git", commit_sha[:8]]
            )

            logger.info(f"Imported commit {commit_sha[:8]} as checkpoint")
            return checkpoint

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to import commit: {e}")
            return None


class CheckpointArchiver:
    """Archive and restore checkpoints"""

    def export_checkpoint_archive(
        self,
        checkpoint: Checkpoint,
        checkpoint_manager: CheckpointManager,
        output_path: Path
    ) -> bool:
        """Export checkpoint as a portable archive

        Args:
            checkpoint: Checkpoint to export
            checkpoint_manager: CheckpointManager instance
            output_path: Path for output .tar.gz file

        Returns:
            True if successful
        """
        try:
            # Create temp directory for archive contents
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)

                # Create metadata file
                metadata = checkpoint.to_dict()
                metadata_file = temp_path / "checkpoint_metadata.json"
                with open(metadata_file, 'w') as f:
                    json.dump(metadata, f, indent=2)

                # Copy snapshot files
                snapshots_dir = temp_path / "snapshots"
                snapshots_dir.mkdir()

                checkpoint_dir = checkpoint_manager._get_checkpoint_dir(
                    checkpoint.checkpoint_id
                )

                for snapshot in checkpoint.snapshots:
                    snapshot_file = checkpoint_dir / f"{snapshot.content_hash}.snapshot"
                    if snapshot_file.exists():
                        dest_file = snapshots_dir / f"{snapshot.content_hash}.snapshot"
                        shutil.copy2(snapshot_file, dest_file)

                # Create tar.gz archive
                with tarfile.open(output_path, "w:gz") as tar:
                    tar.add(temp_path, arcname=".")

            logger.info(f"Exported checkpoint archive to {output_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to export archive: {e}")
            return False

    def import_checkpoint_archive(
        self,
        archive_path: Path,
        checkpoint_manager: CheckpointManager
    ) -> Optional[Checkpoint]:
        """Import checkpoint from archive

        Args:
            archive_path: Path to .tar.gz archive
            checkpoint_manager: CheckpointManager instance

        Returns:
            Imported checkpoint or None
        """
        try:
            # Extract archive to temp directory
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)

                # Extract
                with tarfile.open(archive_path, "r:gz") as tar:
                    tar.extractall(temp_path)

                # Read metadata
                metadata_file = temp_path / "checkpoint_metadata.json"
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)

                # Create checkpoint directory
                checkpoint_id = metadata['checkpoint_id']
                checkpoint_dir = checkpoint_manager._get_checkpoint_dir(checkpoint_id)
                checkpoint_dir.mkdir(parents=True, exist_ok=True)

                # Copy snapshots
                snapshots_dir = temp_path / "snapshots"
                if snapshots_dir.exists():
                    for snapshot_file in snapshots_dir.glob("*.snapshot"):
                        dest_file = checkpoint_dir / snapshot_file.name
                        shutil.copy2(snapshot_file, dest_file)

                # Reconstruct checkpoint object
                snapshots = []
                for snap_data in metadata['snapshots']:
                    snapshot = FileSnapshot(
                        file_path=snap_data['file_path'],
                        original_content=b"",
                        content_hash=snap_data['content_hash'],
                        size_bytes=snap_data['size_bytes'],
                        modified_time=snap_data['modified_time'],
                        compressed=snap_data.get('compressed', False),
                        compressed_size=snap_data.get('compressed_size', 0)
                    )
                    snapshots.append(snapshot)

                checkpoint = Checkpoint(
                    checkpoint_id=checkpoint_id,
                    created_at=metadata['created_at'],
                    description=metadata['description'],
                    operation_type=metadata['operation_type'],
                    snapshots=snapshots,
                    metadata=metadata.get('metadata', {}),
                    tags=metadata.get('tags', [])
                )

                # Add to checkpoint manager
                checkpoint_manager.checkpoints.append(checkpoint)
                checkpoint_manager._save_index()

                logger.info(f"Imported checkpoint from archive")
                return checkpoint

        except Exception as e:
            logger.error(f"Failed to import archive: {e}")
            return None


