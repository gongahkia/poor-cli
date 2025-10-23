"""
Enhanced Tools for poor-cli

Wraps existing tools with checkpoint and diff preview functionality.
"""

from typing import Optional, Dict, Any, List
from pathlib import Path

from poor_cli.tools_async import ToolRegistryAsync
from poor_cli.checkpoint import CheckpointManager
from poor_cli.diff_preview import DiffPreview
from poor_cli.config import Config
from poor_cli.exceptions import setup_logger

logger = setup_logger(__name__)


class EnhancedToolRegistry(ToolRegistryAsync):
    """Enhanced tool registry with checkpoints and diff preview"""

    def __init__(
        self,
        config: Config,
        checkpoint_manager: Optional[CheckpointManager] = None,
        diff_preview: Optional[DiffPreview] = None
    ):
        """Initialize enhanced tools

        Args:
            config: Configuration object
            checkpoint_manager: Optional checkpoint manager
            diff_preview: Optional diff preview
        """
        super().__init__()

        self.config = config
        self.checkpoint_manager = checkpoint_manager
        self.diff_preview = diff_preview

        # Track if diff/checkpoint should be shown for next operation
        self.show_diff = True
        self.create_checkpoint = True

        logger.info("Initialized enhanced tool registry")

    def set_checkpoint_manager(self, checkpoint_manager: CheckpointManager):
        """Set checkpoint manager"""
        self.checkpoint_manager = checkpoint_manager

    def set_diff_preview(self, diff_preview: DiffPreview):
        """Set diff preview"""
        self.diff_preview = diff_preview

    def disable_diff_for_next(self):
        """Disable diff preview for next operation (internal use)"""
        self.show_diff = False

    def disable_checkpoint_for_next(self):
        """Disable checkpoint for next operation (internal use)"""
        self.create_checkpoint = False

    async def write_file_enhanced(
        self,
        file_path: str,
        content: str,
        show_diff: Optional[bool] = None,
        create_checkpoint: Optional[bool] = None
    ) -> str:
        """Enhanced write_file with checkpoint and diff preview

        Args:
            file_path: Path to file
            content: Content to write
            show_diff: Whether to show diff (None = use config)
            create_checkpoint: Whether to create checkpoint (None = use config)

        Returns:
            Result message
        """
        # Determine if we should show diff/checkpoint
        should_show_diff = (
            show_diff if show_diff is not None
            else (self.config.plan_mode.show_diff_in_plan and self.show_diff)
        )

        should_checkpoint = (
            create_checkpoint if create_checkpoint is not None
            else (
                self.config.checkpoint.enabled and
                self.config.checkpoint.auto_checkpoint_before_write and
                self.create_checkpoint
            )
        )

        path = Path(file_path)

        try:
            # Create checkpoint if file exists and checkpointing enabled
            if should_checkpoint and path.exists() and self.checkpoint_manager:
                try:
                    checkpoint = self.checkpoint_manager.create_checkpoint(
                        file_paths=[file_path],
                        description=f"Before writing: {path.name}",
                        operation_type="pre_write"
                    )
                    logger.info(f"Created checkpoint before write: {checkpoint.checkpoint_id}")
                except Exception as e:
                    logger.warning(f"Failed to create checkpoint: {e}")

            # Call parent write_file
            result = await super().write_file(file_path, content)

            # Reset flags
            self.show_diff = True
            self.create_checkpoint = True

            return result

        except Exception as e:
            # Reset flags even on error
            self.show_diff = True
            self.create_checkpoint = True
            raise

    async def edit_file_enhanced(
        self,
        file_path: str,
        new_text: str,
        old_text: Optional[str] = None,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
        show_diff: Optional[bool] = None,
        create_checkpoint: Optional[bool] = None
    ) -> str:
        """Enhanced edit_file with checkpoint and diff preview

        Args:
            file_path: Path to file
            new_text: New text
            old_text: Old text to replace
            start_line: Start line
            end_line: End line
            show_diff: Whether to show diff
            create_checkpoint: Whether to create checkpoint

        Returns:
            Result message
        """
        # Determine if we should checkpoint
        should_checkpoint = (
            create_checkpoint if create_checkpoint is not None
            else (
                self.config.checkpoint.enabled and
                self.config.checkpoint.auto_checkpoint_before_edit and
                self.create_checkpoint
            )
        )

        try:
            # Create checkpoint before edit
            if should_checkpoint and self.checkpoint_manager:
                try:
                    path = Path(file_path)
                    if path.exists():
                        checkpoint = self.checkpoint_manager.create_checkpoint(
                            file_paths=[file_path],
                            description=f"Before editing: {path.name}",
                            operation_type="pre_edit"
                        )
                        logger.info(f"Created checkpoint before edit: {checkpoint.checkpoint_id}")
                except Exception as e:
                    logger.warning(f"Failed to create checkpoint: {e}")

            # Call parent edit_file
            result = await super().edit_file(
                file_path, new_text, old_text, start_line, end_line
            )

            # Reset flags
            self.show_diff = True
            self.create_checkpoint = True

            return result

        except Exception as e:
            # Reset flags even on error
            self.show_diff = True
            self.create_checkpoint = True
            raise

    async def delete_file_enhanced(
        self,
        file_path: str,
        create_checkpoint: Optional[bool] = None
    ) -> str:
        """Enhanced delete_file with checkpoint

        Args:
            file_path: Path to file
            create_checkpoint: Whether to create checkpoint

        Returns:
            Result message
        """
        # Determine if we should checkpoint
        should_checkpoint = (
            create_checkpoint if create_checkpoint is not None
            else (
                self.config.checkpoint.enabled and
                self.config.checkpoint.auto_checkpoint_before_delete and
                self.create_checkpoint
            )
        )

        try:
            # Create checkpoint before delete
            if should_checkpoint and self.checkpoint_manager:
                try:
                    path = Path(file_path)
                    if path.exists():
                        checkpoint = self.checkpoint_manager.create_checkpoint(
                            file_paths=[file_path],
                            description=f"Before deleting: {path.name}",
                            operation_type="pre_delete"
                        )
                        logger.info(f"Created checkpoint before delete: {checkpoint.checkpoint_id}")
                except Exception as e:
                    logger.warning(f"Failed to create checkpoint: {e}")

            # Call parent delete_file
            result = await super().delete_file(file_path)

            # Reset flags
            self.create_checkpoint = True

            return result

        except Exception as e:
            # Reset flags even on error
            self.create_checkpoint = True
            raise

    async def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Execute tool with enhanced functionality

        This wraps the parent execute_tool to use enhanced versions
        of write_file, edit_file, and delete_file when available.
        """
        # Check if we should use enhanced version
        if tool_name == "write_file" and self.checkpoint_manager:
            return await self.write_file_enhanced(**arguments)
        elif tool_name == "edit_file" and self.checkpoint_manager:
            return await self.edit_file_enhanced(**arguments)
        elif tool_name == "delete_file" and self.checkpoint_manager:
            return await self.delete_file_enhanced(**arguments)
        else:
            # Use parent implementation
            return await super().execute_tool(tool_name, arguments)

    def get_checkpoint_stats(self) -> Dict[str, Any]:
        """Get checkpoint statistics"""
        if not self.checkpoint_manager:
            return {}

        checkpoints = self.checkpoint_manager.list_checkpoints(limit=10)
        total_size = self.checkpoint_manager.get_storage_size()

        return {
            "total_checkpoints": len(self.checkpoint_manager.checkpoints),
            "recent_checkpoints": len(checkpoints),
            "storage_size_bytes": total_size,
            "storage_size_mb": total_size / (1024 * 1024)
        }
