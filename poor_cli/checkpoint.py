"""
Checkpoint System for poor-cli

File versioning and rollback without git dependency.
Stores snapshots in .poor-cli/checkpoints/
"""

import os
import json
import shutil
import hashlib
import zlib
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Thread, Event
import time

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
    compressed: bool = False
    compressed_size: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary (excluding content)"""
        result = {
            "file_path": self.file_path,
            "content_hash": self.content_hash,
            "size_bytes": self.size_bytes,
            "modified_time": self.modified_time,
            "compressed": self.compressed
        }
        if self.compressed:
            result["compressed_size"] = self.compressed_size
            result["compression_ratio"] = f"{(1 - self.compressed_size/self.size_bytes) * 100:.1f}%"
        return result


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
    COMPRESSION_THRESHOLD = 1024  # Compress files larger than 1KB
    MAX_WORKERS = 4  # Parallel processing workers

    def __init__(
        self,
        workspace_root: Optional[Path] = None,
        enable_compression: bool = True,
        enable_parallel: bool = True,
        enable_background_cleanup: bool = True
    ):
        """Initialize checkpoint manager

        Args:
            workspace_root: Root directory of workspace (defaults to current directory)
            enable_compression: Enable compression for checkpoints
            enable_parallel: Enable parallel checkpoint creation
            enable_background_cleanup: Enable background cleanup thread
        """
        self.workspace_root = workspace_root or Path.cwd()
        self.checkpoints_dir = self.workspace_root / self.CHECKPOINTS_DIR
        self.index_file = self.checkpoints_dir / self.INDEX_FILE
        self.enable_compression = enable_compression
        self.enable_parallel = enable_parallel

        # Ensure checkpoints directory exists
        self._ensure_checkpoints_dir()

        # Load checkpoint index
        self.checkpoints: List[Checkpoint] = []
        self._load_index()

        # Background cleanup
        self._cleanup_thread: Optional[Thread] = None
        self._cleanup_stop_event = Event()
        if enable_background_cleanup:
            self._start_background_cleanup()

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
                            modified_time=snap_data["modified_time"],
                            compressed=snap_data.get("compressed", False),
                            compressed_size=snap_data.get("compressed_size", 0)
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

            # Create snapshots (parallel or sequential)
            if self.enable_parallel and len(file_paths) > 1:
                snapshots = self._create_snapshots_parallel(file_paths, checkpoint_dir)
            else:
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

            # Determine if compression should be used
            should_compress = (
                self.enable_compression and
                len(content) > self.COMPRESSION_THRESHOLD
            )

            # Compress if needed
            compressed = False
            compressed_size = len(content)
            snapshot_content = content

            if should_compress:
                try:
                    compressed_content = zlib.compress(content, level=9)
                    # Only use compression if it actually reduces size
                    if len(compressed_content) < len(content):
                        snapshot_content = compressed_content
                        compressed = True
                        compressed_size = len(compressed_content)
                        logger.debug(
                            f"Compressed {file_path}: {len(content)} -> {compressed_size} bytes "
                            f"({(1 - compressed_size/len(content)) * 100:.1f}% reduction)"
                        )
                except Exception as e:
                    logger.warning(f"Compression failed for {file_path}: {e}")

            # Save snapshot to checkpoint directory
            snapshot_filename = f"{content_hash}.snapshot"
            snapshot_path = checkpoint_dir / snapshot_filename

            # Only save if not already saved (deduplication)
            if not snapshot_path.exists():
                with open(snapshot_path, 'wb') as f:
                    f.write(snapshot_content)

            # Get file stats
            stat = path.stat()

            # Create snapshot object
            snapshot = FileSnapshot(
                file_path=str(path.absolute()),
                original_content=content,
                content_hash=content_hash,
                size_bytes=len(content),
                modified_time=datetime.fromtimestamp(stat.st_mtime).isoformat(),
                compressed=compressed,
                compressed_size=compressed_size
            )

            return snapshot

        except Exception as e:
            logger.error(f"Failed to snapshot file {file_path}: {e}")
            return None

    def _create_snapshots_parallel(
        self,
        file_paths: List[str],
        checkpoint_dir: Path
    ) -> List[FileSnapshot]:
        """Create snapshots for multiple files in parallel

        Args:
            file_paths: List of file paths to snapshot
            checkpoint_dir: Directory to store snapshots

        Returns:
            List of FileSnapshot objects
        """
        snapshots = []

        with ThreadPoolExecutor(max_workers=self.MAX_WORKERS) as executor:
            # Submit all snapshot tasks
            future_to_path = {
                executor.submit(self._create_file_snapshot, path, checkpoint_dir): path
                for path in file_paths
            }

            # Collect results as they complete
            for future in as_completed(future_to_path):
                file_path = future_to_path[future]
                try:
                    snapshot = future.result()
                    if snapshot:
                        snapshots.append(snapshot)
                except Exception as e:
                    logger.warning(f"Failed to snapshot {file_path}: {e}")

        logger.info(f"Created {len(snapshots)} snapshots in parallel")
        return snapshots

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

        # Decompress if needed
        if snapshot.compressed:
            try:
                content = zlib.decompress(content)
                logger.debug(f"Decompressed snapshot for {snapshot.file_path}")
            except Exception as e:
                logger.error(f"Failed to decompress snapshot: {e}")
                raise FileOperationError(f"Snapshot decompression failed: {e}")

        # Verify hash (of decompressed content)
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

    def _start_background_cleanup(self):
        """Start background cleanup thread"""
        def cleanup_worker():
            """Background worker for periodic cleanup"""
            while not self._cleanup_stop_event.is_set():
                try:
                    # Wait 5 minutes before each cleanup check
                    if self._cleanup_stop_event.wait(timeout=300):
                        break

                    # Run cleanup
                    if len(self.checkpoints) > self.MAX_CHECKPOINTS:
                        logger.info("Running background checkpoint cleanup")
                        self._cleanup_old_checkpoints()

                except Exception as e:
                    logger.error(f"Background cleanup error: {e}")

        self._cleanup_thread = Thread(target=cleanup_worker, daemon=True, name="CheckpointCleanup")
        self._cleanup_thread.start()
        logger.info("Started background cleanup thread")

    def stop_background_cleanup(self):
        """Stop background cleanup thread"""
        if self._cleanup_thread and self._cleanup_thread.is_alive():
            self._cleanup_stop_event.set()
            self._cleanup_thread.join(timeout=2.0)
            logger.info("Stopped background cleanup thread")

    def get_compression_stats(self) -> Dict[str, Any]:
        """Get compression statistics for all checkpoints

        Returns:
            Dictionary with compression statistics
        """
        total_snapshots = 0
        compressed_snapshots = 0
        total_original_size = 0
        total_compressed_size = 0

        for checkpoint in self.checkpoints:
            for snapshot in checkpoint.snapshots:
                total_snapshots += 1
                total_original_size += snapshot.size_bytes

                if snapshot.compressed:
                    compressed_snapshots += 1
                    total_compressed_size += snapshot.compressed_size
                else:
                    total_compressed_size += snapshot.size_bytes

        compression_ratio = 0
        if total_original_size > 0:
            compression_ratio = (1 - total_compressed_size / total_original_size) * 100

        return {
            "total_snapshots": total_snapshots,
            "compressed_snapshots": compressed_snapshots,
            "uncompressed_snapshots": total_snapshots - compressed_snapshots,
            "compression_percentage": f"{(compressed_snapshots/total_snapshots*100) if total_snapshots > 0 else 0:.1f}%",
            "total_original_size_bytes": total_original_size,
            "total_compressed_size_bytes": total_compressed_size,
            "space_saved_bytes": total_original_size - total_compressed_size,
            "overall_compression_ratio": f"{compression_ratio:.1f}%"
        }

    def __del__(self):
        """Cleanup on destruction"""
        self.stop_background_cleanup()
