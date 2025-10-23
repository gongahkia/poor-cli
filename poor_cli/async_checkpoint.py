"""
Async checkpoint creation for poor-cli

Provides non-blocking checkpoint creation for large files.
"""

import asyncio
from pathlib import Path
from typing import List, Optional, Callable, Awaitable
from poor_cli.checkpoint import CheckpointManager, Checkpoint, FileSnapshot
from poor_cli.exceptions import FileOperationError, setup_logger

logger = setup_logger(__name__)


class AsyncCheckpointManager(CheckpointManager):
    """Async checkpoint manager with progress reporting"""

    async def create_checkpoint_async(
        self,
        file_paths: List[str],
        description: str,
        operation_type: str = "manual",
        tags: Optional[List[str]] = None,
        progress_callback: Optional[Callable[[int, int, str], Awaitable[None]]] = None
    ) -> Checkpoint:
        """Create checkpoint asynchronously with progress reporting

        Args:
            file_paths: List of file paths to snapshot
            description: Human-readable description
            operation_type: Type of operation
            tags: Optional tags
            progress_callback: Optional async callback(current, total, file_name)

        Returns:
            Created Checkpoint
        """
        checkpoint_id = self._generate_checkpoint_id()
        checkpoint_dir = self._get_checkpoint_dir(checkpoint_id)

        try:
            # Create checkpoint directory
            checkpoint_dir.mkdir(parents=True, exist_ok=True)

            # Create snapshots concurrently
            total_files = len(file_paths)
            tasks = []

            for idx, file_path in enumerate(file_paths):
                task = self._create_file_snapshot_async(
                    file_path,
                    checkpoint_dir,
                    idx,
                    total_files,
                    progress_callback
                )
                tasks.append(task)

            # Execute all snapshots concurrently
            snapshots = await asyncio.gather(*tasks, return_exceptions=True)

            # Filter out None and exceptions
            valid_snapshots = []
            for snapshot in snapshots:
                if isinstance(snapshot, Exception):
                    logger.warning(f"Failed to create snapshot: {snapshot}")
                elif snapshot is not None:
                    valid_snapshots.append(snapshot)

            # Create checkpoint
            from datetime import datetime
            checkpoint = Checkpoint(
                checkpoint_id=checkpoint_id,
                created_at=datetime.now().isoformat(),
                description=description,
                operation_type=operation_type,
                snapshots=valid_snapshots,
                tags=tags or []
            )

            # Add to index and save
            self.checkpoints.append(checkpoint)
            self._save_index()

            # Cleanup old checkpoints
            self._cleanup_old_checkpoints()

            logger.info(
                f"Created async checkpoint {checkpoint_id} with {len(valid_snapshots)} file(s)"
            )

            return checkpoint

        except Exception as e:
            logger.error(f"Failed to create async checkpoint: {e}")
            # Cleanup on failure
            import shutil
            if checkpoint_dir.exists():
                shutil.rmtree(checkpoint_dir, ignore_errors=True)
            raise FileOperationError("Failed to create async checkpoint", str(e))

    async def _create_file_snapshot_async(
        self,
        file_path: str,
        checkpoint_dir: Path,
        current_idx: int,
        total_files: int,
        progress_callback: Optional[Callable[[int, int, str], Awaitable[None]]]
    ) -> Optional[FileSnapshot]:
        """Create file snapshot asynchronously

        Args:
            file_path: Path to file
            checkpoint_dir: Checkpoint directory
            current_idx: Current file index
            total_files: Total number of files
            progress_callback: Progress callback

        Returns:
            FileSnapshot or None if file doesn't exist
        """
        # Report progress
        if progress_callback:
            await progress_callback(current_idx + 1, total_files, file_path)

        # Use thread pool for file I/O
        return await asyncio.to_thread(
            self._create_file_snapshot,
            file_path,
            checkpoint_dir
        )

    async def restore_checkpoint_async(
        self,
        checkpoint_id: str,
        file_paths: Optional[List[str]] = None,
        progress_callback: Optional[Callable[[int, int, str], Awaitable[None]]] = None
    ) -> int:
        """Restore checkpoint asynchronously with progress

        Args:
            checkpoint_id: ID of checkpoint
            file_paths: Optional specific files to restore
            progress_callback: Progress callback

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

        # Filter snapshots
        snapshots_to_restore = [
            s for s in checkpoint.snapshots
            if file_paths is None or s.file_path in file_paths
        ]

        total_snapshots = len(snapshots_to_restore)
        tasks = []

        for idx, snapshot in enumerate(snapshots_to_restore):
            task = self._restore_file_snapshot_async(
                snapshot,
                checkpoint_dir,
                idx,
                total_snapshots,
                progress_callback
            )
            tasks.append(task)

        # Restore concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Count successes
        restored_count = sum(1 for r in results if r is True)

        logger.info(
            f"Restored {restored_count}/{total_snapshots} file(s) from checkpoint {checkpoint_id}"
        )

        return restored_count

    async def _restore_file_snapshot_async(
        self,
        snapshot: FileSnapshot,
        checkpoint_dir: Path,
        current_idx: int,
        total_snapshots: int,
        progress_callback: Optional[Callable[[int, int, str], Awaitable[None]]]
    ) -> bool:
        """Restore single file snapshot asynchronously

        Args:
            snapshot: FileSnapshot to restore
            checkpoint_dir: Checkpoint directory
            current_idx: Current index
            total_snapshots: Total snapshots
            progress_callback: Progress callback

        Returns:
            True if successful, False otherwise
        """
        # Report progress
        if progress_callback:
            await progress_callback(current_idx + 1, total_snapshots, snapshot.file_path)

        # Use thread pool for file I/O
        try:
            await asyncio.to_thread(
                self._restore_file_snapshot,
                snapshot,
                checkpoint_dir
            )
            return True
        except Exception as e:
            logger.error(f"Failed to restore {snapshot.file_path}: {e}")
            return False

    async def create_checkpoint_with_limit_async(
        self,
        file_paths: List[str],
        description: str,
        max_size_mb: int = 100,
        **kwargs
    ) -> Checkpoint:
        """Create checkpoint with size limit check

        Args:
            file_paths: Files to checkpoint
            description: Description
            max_size_mb: Maximum total size in MB
            **kwargs: Additional args for create_checkpoint_async

        Returns:
            Created checkpoint

        Raises:
            FileOperationError: If total size exceeds limit
        """
        # Calculate total size asynchronously
        total_size = 0
        for file_path in file_paths:
            path = Path(file_path)
            if path.exists():
                total_size += await asyncio.to_thread(path.stat().st_size)

        total_size_mb = total_size / (1024 * 1024)

        if total_size_mb > max_size_mb:
            raise FileOperationError(
                f"Checkpoint size ({total_size_mb:.1f}MB) exceeds limit ({max_size_mb}MB)",
                "Consider checkpointing fewer files or increasing limit"
            )

        logger.info(f"Creating checkpoint of {total_size_mb:.1f}MB")

        return await self.create_checkpoint_async(
            file_paths,
            description,
            **kwargs
        )
