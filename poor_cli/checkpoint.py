"""
Checkpoint System for poor-cli

File versioning and rollback without git dependency.
Stores snapshots in .poor-cli/checkpoints/
"""

import os
import json
import shutil
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime

from poor_cli.exceptions import FileOperationError, setup_logger

logger = setup_logger(__name__)


@dataclass
class FileSnapshot:
    """Snapshot of a single file"""
    file_path: str
    original_content: bytes
    content_hash: str
    size_bytes: int
    modified_time: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary (excluding content)"""
        return {
            "file_path": self.file_path,
            "content_hash": self.content_hash,
            "size_bytes": self.size_bytes,
            "modified_time": self.modified_time
        }


@dataclass
class Checkpoint:
    """A checkpoint representing workspace state"""
    checkpoint_id: str
    created_at: str
    description: str
    operation_type: str  # 'manual', 'auto', 'pre_write', 'pre_edit', etc.
    snapshots: List[FileSnapshot] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)

    def get_file_count(self) -> int:
        """Get number of files in checkpoint"""
        return len(self.snapshots)

    def get_total_size(self) -> int:
        """Get total size of all snapshots"""
        return sum(s.size_bytes for s in self.snapshots)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary (for metadata file)"""
        return {
            "checkpoint_id": self.checkpoint_id,
            "created_at": self.created_at,
            "description": self.description,
            "operation_type": self.operation_type,
            "snapshots": [s.to_dict() for s in self.snapshots],
            "metadata": self.metadata,
            "tags": self.tags,
            "file_count": self.get_file_count(),
            "total_size_bytes": self.get_total_size()
        }


class CheckpointManager:
    """Manages checkpoints for file versioning and rollback"""

    CHECKPOINTS_DIR = ".poor-cli/checkpoints"
    INDEX_FILE = "checkpoint_index.json"
    MAX_CHECKPOINTS = 50  # Keep last 50 checkpoints

    def __init__(self, workspace_root: Optional[Path] = None):
        """Initialize checkpoint manager

        Args:
            workspace_root: Root directory of workspace (defaults to current directory)
        """
        self.workspace_root = workspace_root or Path.cwd()
        self.checkpoints_dir = self.workspace_root / self.CHECKPOINTS_DIR
        self.index_file = self.checkpoints_dir / self.INDEX_FILE

        # Ensure checkpoints directory exists
        self._ensure_checkpoints_dir()

        # Load checkpoint index
        self.checkpoints: List[Checkpoint] = []
        self._load_index()

        logger.info(f"Initialized checkpoint manager at {self.checkpoints_dir}")

    def _ensure_checkpoints_dir(self):
        """Ensure checkpoints directory exists"""
        try:
            self.checkpoints_dir.mkdir(parents=True, exist_ok=True)

            # Create .gitignore to exclude checkpoint data
            gitignore_path = self.checkpoints_dir / ".gitignore"
            if not gitignore_path.exists():
                with open(gitignore_path, 'w') as f:
                    f.write("# Exclude checkpoint data\n")
                    f.write("*.snapshot\n")
                    f.write("checkpoint_*/\n")
                    f.write("# Keep index\n")
                    f.write("!checkpoint_index.json\n")

        except Exception as e:
            logger.error(f"Failed to create checkpoints directory: {e}")
            raise FileOperationError("Failed to initialize checkpoints", str(e))

    def _load_index(self):
        """Load checkpoint index from disk"""
        try:
            if self.index_file.exists():
                with open(self.index_file, 'r') as f:
                    data = json.load(f)

                # Load checkpoint metadata (not file content)
                for cp_data in data.get("checkpoints", []):
                    # Reconstruct FileSnapshot objects without content
                    snapshots = []
                    for snap_data in cp_data.get("snapshots", []):
                        snapshot = FileSnapshot(
                            file_path=snap_data["file_path"],
                            original_content=b"",  # Don't load content in memory
                            content_hash=snap_data["content_hash"],
                            size_bytes=snap_data["size_bytes"],
                            modified_time=snap_data["modified_time"]
                        )
                        snapshots.append(snapshot)

                    checkpoint = Checkpoint(
                        checkpoint_id=cp_data["checkpoint_id"],
                        created_at=cp_data["created_at"],
                        description=cp_data["description"],
                        operation_type=cp_data["operation_type"],
                        snapshots=snapshots,
                        metadata=cp_data.get("metadata", {}),
                        tags=cp_data.get("tags", [])
                    )
                    self.checkpoints.append(checkpoint)

                logger.info(f"Loaded {len(self.checkpoints)} checkpoints from index")

        except Exception as e:
            logger.warning(f"Failed to load checkpoint index: {e}")
            self.checkpoints = []

    def _save_index(self):
        """Save checkpoint index to disk"""
        try:
            data = {
                "version": "1.0",
                "workspace_root": str(self.workspace_root),
                "last_updated": datetime.now().isoformat(),
                "checkpoints": [cp.to_dict() for cp in self.checkpoints]
            }

            with open(self.index_file, 'w') as f:
                json.dump(data, f, indent=2)

            logger.debug("Saved checkpoint index")

        except Exception as e:
            logger.error(f"Failed to save checkpoint index: {e}")
            raise FileOperationError("Failed to save checkpoint index", str(e))

    def _generate_checkpoint_id(self) -> str:
        """Generate unique checkpoint ID"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        return f"cp_{timestamp}"

    def _get_checkpoint_dir(self, checkpoint_id: str) -> Path:
        """Get directory path for a checkpoint"""
        return self.checkpoints_dir / checkpoint_id

    def _compute_file_hash(self, content: bytes) -> str:
        """Compute SHA256 hash of file content"""
        return hashlib.sha256(content).hexdigest()[:16]

    def create_checkpoint(
        self,
        file_paths: List[str],
        description: str,
        operation_type: str = "manual",
        tags: Optional[List[str]] = None
    ) -> Checkpoint:
        """Create a checkpoint for specified files

        Args:
            file_paths: List of file paths to snapshot
            description: Human-readable description
            operation_type: Type of operation triggering checkpoint
            tags: Optional tags for categorization

        Returns:
            Created Checkpoint object
        """
        checkpoint_id = self._generate_checkpoint_id()
        checkpoint_dir = self._get_checkpoint_dir(checkpoint_id)

        try:
            # Create checkpoint directory
            checkpoint_dir.mkdir(parents=True, exist_ok=True)

            # Create snapshots
            snapshots = []
            for file_path in file_paths:
                try:
                    snapshot = self._create_file_snapshot(file_path, checkpoint_dir)
                    if snapshot:
                        snapshots.append(snapshot)
                except Exception as e:
                    logger.warning(f"Failed to snapshot {file_path}: {e}")
                    continue

            # Create checkpoint
            checkpoint = Checkpoint(
                checkpoint_id=checkpoint_id,
                created_at=datetime.now().isoformat(),
                description=description,
                operation_type=operation_type,
                snapshots=snapshots,
                tags=tags or []
            )

            # Add to index and save
            self.checkpoints.append(checkpoint)
            self._save_index()

            # Cleanup old checkpoints
            self._cleanup_old_checkpoints()

            logger.info(
                f"Created checkpoint {checkpoint_id} with {len(snapshots)} file(s)"
            )

            return checkpoint

        except Exception as e:
            logger.error(f"Failed to create checkpoint: {e}")
            # Cleanup on failure
            if checkpoint_dir.exists():
                shutil.rmtree(checkpoint_dir, ignore_errors=True)
            raise FileOperationError("Failed to create checkpoint", str(e))

    def _create_file_snapshot(
        self,
        file_path: str,
        checkpoint_dir: Path
    ) -> Optional[FileSnapshot]:
        """Create a snapshot of a single file

        Args:
            file_path: Path to file
            checkpoint_dir: Directory to store snapshot

        Returns:
            FileSnapshot object or None if file doesn't exist
        """
        path = Path(file_path)

        # Check if file exists
        if not path.exists():
            logger.debug(f"File doesn't exist, skipping: {file_path}")
            return None

        # Read file content
        try:
            with open(path, 'rb') as f:
                content = f.read()

            # Compute hash
            content_hash = self._compute_file_hash(content)

            # Save snapshot to checkpoint directory
            snapshot_filename = f"{content_hash}.snapshot"
            snapshot_path = checkpoint_dir / snapshot_filename

            # Only save if not already saved (deduplication)
            if not snapshot_path.exists():
                with open(snapshot_path, 'wb') as f:
                    f.write(content)

            # Get file stats
            stat = path.stat()

            # Create snapshot object
            snapshot = FileSnapshot(
                file_path=str(path.absolute()),
                original_content=content,
                content_hash=content_hash,
                size_bytes=len(content),
                modified_time=datetime.fromtimestamp(stat.st_mtime).isoformat()
            )

            return snapshot

        except Exception as e:
            logger.error(f"Failed to snapshot file {file_path}: {e}")
            return None

    def restore_checkpoint(
        self,
        checkpoint_id: str,
        file_paths: Optional[List[str]] = None
    ) -> int:
        """Restore files from a checkpoint

        Args:
            checkpoint_id: ID of checkpoint to restore
            file_paths: Optional list of specific files to restore (None = all)

        Returns:
            Number of files restored
        """
        # Find checkpoint
        checkpoint = self.get_checkpoint(checkpoint_id)
        if not checkpoint:
            raise FileOperationError(f"Checkpoint not found: {checkpoint_id}")

        checkpoint_dir = self._get_checkpoint_dir(checkpoint_id)
        if not checkpoint_dir.exists():
            raise FileOperationError(f"Checkpoint data missing: {checkpoint_id}")

        restored_count = 0

        try:
            # Restore snapshots
            for snapshot in checkpoint.snapshots:
                # Skip if specific files requested and this isn't one of them
                if file_paths and snapshot.file_path not in file_paths:
                    continue

                # Restore file
                try:
                    self._restore_file_snapshot(snapshot, checkpoint_dir)
                    restored_count += 1
                except Exception as e:
                    logger.error(f"Failed to restore {snapshot.file_path}: {e}")
                    continue

            logger.info(
                f"Restored {restored_count} file(s) from checkpoint {checkpoint_id}"
            )

            return restored_count

        except Exception as e:
            logger.error(f"Failed to restore checkpoint: {e}")
            raise FileOperationError("Failed to restore checkpoint", str(e))

    def _restore_file_snapshot(self, snapshot: FileSnapshot, checkpoint_dir: Path):
        """Restore a single file from snapshot"""
        # Get snapshot file
        snapshot_filename = f"{snapshot.content_hash}.snapshot"
        snapshot_path = checkpoint_dir / snapshot_filename

        if not snapshot_path.exists():
            raise FileOperationError(f"Snapshot file missing: {snapshot_filename}")

        # Read snapshot content
        with open(snapshot_path, 'rb') as f:
            content = f.read()

        # Verify hash
        actual_hash = self._compute_file_hash(content)
        if actual_hash != snapshot.content_hash:
            raise FileOperationError(f"Snapshot corrupted: hash mismatch")

        # Create parent directories if needed
        file_path = Path(snapshot.file_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Write file
        with open(file_path, 'wb') as f:
            f.write(content)

        logger.debug(f"Restored file: {snapshot.file_path}")

    def list_checkpoints(
        self,
        limit: Optional[int] = None,
        operation_type: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> List[Checkpoint]:
        """List checkpoints with optional filtering

        Args:
            limit: Maximum number of checkpoints to return
            operation_type: Filter by operation type
            tags: Filter by tags

        Returns:
            List of checkpoints (most recent first)
        """
        # Filter checkpoints
        filtered = self.checkpoints

        if operation_type:
            filtered = [cp for cp in filtered if cp.operation_type == operation_type]

        if tags:
            filtered = [
                cp for cp in filtered
                if any(tag in cp.tags for tag in tags)
            ]

        # Sort by creation time (most recent first)
        filtered.sort(key=lambda cp: cp.created_at, reverse=True)

        # Apply limit
        if limit:
            filtered = filtered[:limit]

        return filtered

    def get_checkpoint(self, checkpoint_id: str) -> Optional[Checkpoint]:
        """Get a checkpoint by ID"""
        for checkpoint in self.checkpoints:
            if checkpoint.checkpoint_id == checkpoint_id:
                return checkpoint
        return None

    def delete_checkpoint(self, checkpoint_id: str):
        """Delete a checkpoint"""
        checkpoint = self.get_checkpoint(checkpoint_id)
        if not checkpoint:
            raise FileOperationError(f"Checkpoint not found: {checkpoint_id}")

        try:
            # Delete checkpoint directory
            checkpoint_dir = self._get_checkpoint_dir(checkpoint_id)
            if checkpoint_dir.exists():
                shutil.rmtree(checkpoint_dir)

            # Remove from index
            self.checkpoints = [
                cp for cp in self.checkpoints
                if cp.checkpoint_id != checkpoint_id
            ]
            self._save_index()

            logger.info(f"Deleted checkpoint {checkpoint_id}")

        except Exception as e:
            logger.error(f"Failed to delete checkpoint: {e}")
            raise FileOperationError("Failed to delete checkpoint", str(e))

    def _cleanup_old_checkpoints(self):
        """Remove old checkpoints if over limit"""
        if len(self.checkpoints) <= self.MAX_CHECKPOINTS:
            return

        # Sort by creation time
        sorted_checkpoints = sorted(
            self.checkpoints,
            key=lambda cp: cp.created_at,
            reverse=True
        )

        # Keep only recent ones
        to_keep = sorted_checkpoints[:self.MAX_CHECKPOINTS]
        to_delete = sorted_checkpoints[self.MAX_CHECKPOINTS:]

        # Delete old checkpoints
        for checkpoint in to_delete:
            try:
                self.delete_checkpoint(checkpoint.checkpoint_id)
            except Exception as e:
                logger.warning(f"Failed to cleanup checkpoint {checkpoint.checkpoint_id}: {e}")

        logger.info(f"Cleaned up {len(to_delete)} old checkpoint(s)")

    def get_storage_size(self) -> int:
        """Get total storage size used by checkpoints"""
        total_size = 0
        if self.checkpoints_dir.exists():
            for root, dirs, files in os.walk(self.checkpoints_dir):
                for file in files:
                    file_path = Path(root) / file
                    try:
                        total_size += file_path.stat().st_size
                    except:
                        continue
        return total_size
