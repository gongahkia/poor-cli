"""
Checkpoint Integration Tools for poor-cli

Integrations with external systems:
- Export checkpoints as git commits
- Cloud backup (S3, Google Cloud Storage, Azure)
- Import/export checkpoint archives
- Sync checkpoints between machines
"""

import os
import subprocess
import json
import tarfile
import tempfile
import hashlib
from pathlib import Path
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import shutil

from poor_cli.checkpoint import Checkpoint, CheckpointManager, FileSnapshot
from poor_cli.exceptions import FileOperationError, setup_logger

logger = setup_logger(__name__)


class CloudProvider(Enum):
    """Supported cloud storage providers"""
    S3 = "s3"
    GCS = "gcs"
    AZURE = "azure"
    DROPBOX = "dropbox"
    LOCAL = "local"


@dataclass
class CloudConfig:
    """Cloud storage configuration"""
    provider: CloudProvider
    bucket_name: str
    credentials_path: Optional[str] = None
    region: Optional[str] = None
    endpoint_url: Optional[str] = None


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
            except:
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


class CloudBackup:
    """Cloud backup for checkpoints"""

    def __init__(self, config: CloudConfig):
        self.config = config
        self._client = None

    def _init_client(self):
        """Initialize cloud storage client"""
        if self._client:
            return

        if self.config.provider == CloudProvider.S3:
            try:
                import boto3
                session_kwargs = {}
                if self.config.credentials_path:
                    session_kwargs['profile_name'] = self.config.credentials_path

                self._client = boto3.client(
                    's3',
                    region_name=self.config.region,
                    endpoint_url=self.config.endpoint_url,
                    **session_kwargs
                )
                logger.info("Initialized S3 client")
            except ImportError:
                logger.error("boto3 not installed - install with: pip install boto3")
                raise

        elif self.config.provider == CloudProvider.GCS:
            try:
                from google.cloud import storage
                if self.config.credentials_path:
                    self._client = storage.Client.from_service_account_json(
                        self.config.credentials_path
                    )
                else:
                    self._client = storage.Client()
                logger.info("Initialized GCS client")
            except ImportError:
                logger.error("google-cloud-storage not installed - install with: pip install google-cloud-storage")
                raise

        elif self.config.provider == CloudProvider.AZURE:
            try:
                from azure.storage.blob import BlobServiceClient
                if self.config.credentials_path:
                    with open(self.config.credentials_path, 'r') as f:
                        connection_string = f.read().strip()
                    self._client = BlobServiceClient.from_connection_string(connection_string)
                logger.info("Initialized Azure client")
            except ImportError:
                logger.error("azure-storage-blob not installed - install with: pip install azure-storage-blob")
                raise

    def upload_checkpoint(
        self,
        checkpoint: Checkpoint,
        checkpoint_manager: CheckpointManager,
        archive_path: Optional[Path] = None
    ) -> bool:
        """Upload checkpoint to cloud storage

        Args:
            checkpoint: Checkpoint to upload
            checkpoint_manager: CheckpointManager instance
            archive_path: Pre-created archive (creates temp if None)

        Returns:
            True if successful
        """
        try:
            self._init_client()

            # Create archive if not provided
            if not archive_path:
                temp_dir = Path(tempfile.mkdtemp())
                archive_path = temp_dir / f"{checkpoint.checkpoint_id}.tar.gz"

                archiver = CheckpointArchiver()
                if not archiver.export_checkpoint_archive(
                    checkpoint, checkpoint_manager, archive_path
                ):
                    return False

            # Upload based on provider
            object_key = f"checkpoints/{checkpoint.checkpoint_id}.tar.gz"

            if self.config.provider == CloudProvider.S3:
                self._client.upload_file(
                    str(archive_path),
                    self.config.bucket_name,
                    object_key
                )

            elif self.config.provider == CloudProvider.GCS:
                bucket = self._client.bucket(self.config.bucket_name)
                blob = bucket.blob(object_key)
                blob.upload_from_filename(str(archive_path))

            elif self.config.provider == CloudProvider.AZURE:
                blob_client = self._client.get_blob_client(
                    container=self.config.bucket_name,
                    blob=object_key
                )
                with open(archive_path, 'rb') as f:
                    blob_client.upload_blob(f, overwrite=True)

            logger.info(f"Uploaded checkpoint to {self.config.provider.value}")
            return True

        except Exception as e:
            logger.error(f"Failed to upload checkpoint: {e}")
            return False

    def download_checkpoint(
        self,
        checkpoint_id: str,
        checkpoint_manager: CheckpointManager
    ) -> Optional[Checkpoint]:
        """Download checkpoint from cloud storage

        Args:
            checkpoint_id: Checkpoint ID to download
            checkpoint_manager: CheckpointManager instance

        Returns:
            Downloaded checkpoint or None
        """
        try:
            self._init_client()

            # Download archive
            object_key = f"checkpoints/{checkpoint_id}.tar.gz"
            temp_dir = Path(tempfile.mkdtemp())
            archive_path = temp_dir / f"{checkpoint_id}.tar.gz"

            if self.config.provider == CloudProvider.S3:
                self._client.download_file(
                    self.config.bucket_name,
                    object_key,
                    str(archive_path)
                )

            elif self.config.provider == CloudProvider.GCS:
                bucket = self._client.bucket(self.config.bucket_name)
                blob = bucket.blob(object_key)
                blob.download_to_filename(str(archive_path))

            elif self.config.provider == CloudProvider.AZURE:
                blob_client = self._client.get_blob_client(
                    container=self.config.bucket_name,
                    blob=object_key
                )
                with open(archive_path, 'wb') as f:
                    blob_client.download_blob().readinto(f)

            # Import archive
            archiver = CheckpointArchiver()
            checkpoint = archiver.import_checkpoint_archive(
                archive_path, checkpoint_manager
            )

            logger.info(f"Downloaded checkpoint from {self.config.provider.value}")
            return checkpoint

        except Exception as e:
            logger.error(f"Failed to download checkpoint: {e}")
            return None

    def list_remote_checkpoints(self) -> List[str]:
        """List checkpoints available in cloud storage

        Returns:
            List of checkpoint IDs
        """
        try:
            self._init_client()

            checkpoint_ids = []

            if self.config.provider == CloudProvider.S3:
                response = self._client.list_objects_v2(
                    Bucket=self.config.bucket_name,
                    Prefix="checkpoints/"
                )
                for obj in response.get('Contents', []):
                    key = obj['Key']
                    if key.endswith('.tar.gz'):
                        checkpoint_id = Path(key).stem
                        checkpoint_ids.append(checkpoint_id)

            elif self.config.provider == CloudProvider.GCS:
                bucket = self._client.bucket(self.config.bucket_name)
                blobs = bucket.list_blobs(prefix="checkpoints/")
                for blob in blobs:
                    if blob.name.endswith('.tar.gz'):
                        checkpoint_id = Path(blob.name).stem
                        checkpoint_ids.append(checkpoint_id)

            elif self.config.provider == CloudProvider.AZURE:
                container_client = self._client.get_container_client(
                    self.config.bucket_name
                )
                blobs = container_client.list_blobs(name_starts_with="checkpoints/")
                for blob in blobs:
                    if blob.name.endswith('.tar.gz'):
                        checkpoint_id = Path(blob.name).stem
                        checkpoint_ids.append(checkpoint_id)

            return checkpoint_ids

        except Exception as e:
            logger.error(f"Failed to list remote checkpoints: {e}")
            return []
