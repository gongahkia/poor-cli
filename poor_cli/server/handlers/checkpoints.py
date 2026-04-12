# ruff: noqa: F403,F405
from __future__ import annotations

from poor_cli.server.handler_deps import *
from poor_cli.server.registry import register


class CheckpointsHandlersMixin:
    async def handle_list_checkpoints(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List available checkpoints with storage metadata."""
        self._ensure_initialized()

        manager = self.core.checkpoint_manager
        if manager is None:
            return {
                "available": False,
                "checkpoints": [],
                "storageSizeBytes": 0,
                "storagePath": "",
            }

        limit = self._clamp_count(params.get("limit"), default=20, min_value=1, max_value=200)
        checkpoints = manager.list_checkpoints(limit=limit)
        return {
            "available": True,
            "checkpoints": [
                {
                    "checkpointId": cp.checkpoint_id,
                    "createdAt": cp.created_at,
                    "description": cp.description,
                    "operationType": cp.operation_type,
                    "fileCount": cp.get_file_count(),
                    "totalSizeBytes": cp.get_total_size(),
                    "tags": cp.tags,
                }
                for cp in checkpoints
            ],
            "storageSizeBytes": manager.get_storage_size(),
            "storagePath": str(manager.checkpoints_dir),
        }

    def _discover_default_checkpoint_files(self, limit: int = 10) -> List[str]:
        files: List[str] = []
        for path in Path.cwd().rglob("*.py"):
            if not path.is_file():
                continue
            path_parts = set(path.parts)
            if ".git" in path_parts or ".poor-cli" in path_parts:
                continue
            files.append(str(path.resolve()))
            if len(files) >= limit:
                break
        return files

    async def handle_create_checkpoint(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Create a manual checkpoint and return summary metadata."""
        self._ensure_initialized()

        manager = self.core.checkpoint_manager
        if manager is None:
            raise PoorCLIError("Checkpoint system not available")

        description = str(params.get("description", "Manual checkpoint")).strip() or "Manual checkpoint"
        operation_type = str(params.get("operationType", "manual")).strip() or "manual"

        raw_file_paths = params.get("filePaths")
        file_paths: List[str]
        if raw_file_paths is None:
            file_paths = self._discover_default_checkpoint_files(limit=10)
        elif isinstance(raw_file_paths, list):
            file_paths = [str(self._resolve_path(str(path))) for path in raw_file_paths if str(path).strip()]
        else:
            raise InvalidParamsError("filePaths must be a list of file paths")

        if not file_paths:
            raise PoorCLIError("No files found to checkpoint")

        raw_tags = params.get("tags")
        tags: Optional[List[str]] = None
        if isinstance(raw_tags, list):
            tags = [str(tag).strip() for tag in raw_tags if str(tag).strip()]

        checkpoint = await asyncio.to_thread(
            manager.create_checkpoint,
            file_paths,
            description,
            operation_type,
            tags,
        )

        return {
            "checkpointId": checkpoint.checkpoint_id,
            "createdAt": checkpoint.created_at,
            "description": checkpoint.description,
            "operationType": checkpoint.operation_type,
            "fileCount": checkpoint.get_file_count(),
            "totalSizeBytes": checkpoint.get_total_size(),
            "tags": checkpoint.tags,
        }

    async def handle_restore_checkpoint(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Restore a checkpoint by ID (or restore the latest checkpoint)."""
        self._ensure_initialized()

        manager = self.core.checkpoint_manager
        if manager is None:
            raise PoorCLIError("Checkpoint system not available")

        requested_id = str(params.get("checkpointId", "")).strip()
        if not requested_id or requested_id == "last":
            checkpoints = manager.list_checkpoints(limit=1)
            if not checkpoints:
                raise PoorCLIError("No checkpoints available to restore")
            checkpoint = checkpoints[0]
        else:
            checkpoint = manager.get_checkpoint(requested_id)
            if checkpoint is None:
                raise InvalidParamsError(f"Checkpoint not found: {requested_id}")

        restored_count = await asyncio.to_thread(
            manager.restore_checkpoint,
            checkpoint.checkpoint_id,
        )

        return {
            "checkpointId": checkpoint.checkpoint_id,
            "restoredFiles": restored_count,
            "description": checkpoint.description,
            "createdAt": checkpoint.created_at,
        }

    async def handle_preview_checkpoint(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Preview what restoring a checkpoint would change."""
        self._ensure_initialized()
        manager = self.core.checkpoint_manager
        if manager is None:
            raise PoorCLIError("Checkpoint system not available")
        checkpoint_id = str(params.get("checkpointId", "")).strip()
        if not checkpoint_id:
            raise InvalidParamsError("checkpointId is required")
        files = await asyncio.to_thread(manager.preview_checkpoint, checkpoint_id)
        return {"checkpointId": checkpoint_id, "files": files}

    async def handle_compare_files(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return a unified diff for two files."""
        self._ensure_initialized()

        file1 = str(params.get("file1", "")).strip()
        file2 = str(params.get("file2", "")).strip()
        if not file1 or not file2:
            raise InvalidParamsError("Missing file paths. Usage: /diff <file1> <file2>")

        path1 = self._resolve_path(file1)
        path2 = self._resolve_path(file2)
        if not path1.is_file():
            raise InvalidParamsError(f"File not found: {file1}")
        if not path2.is_file():
            raise InvalidParamsError(f"File not found: {file2}")

        text1 = path1.read_text(encoding="utf-8", errors="ignore")
        text2 = path2.read_text(encoding="utf-8", errors="ignore")
        diff = "".join(
            difflib.unified_diff(
                text1.splitlines(keepends=True),
                text2.splitlines(keepends=True),
                fromfile=str(path1),
                tofile=str(path2),
            )
        )
        if not diff:
            diff = "(No differences)"

        return {"diff": diff}

@register('poor-cli/listCheckpoints')
async def _rpc_73(ctx, params):
    return await ctx.handle_list_checkpoints(params)

@register('poor-cli/createCheckpoint')
async def _rpc_74(ctx, params):
    return await ctx.handle_create_checkpoint(params)

@register('poor-cli/restoreCheckpoint')
async def _rpc_75(ctx, params):
    return await ctx.handle_restore_checkpoint(params)

@register('poor-cli/previewCheckpoint')
async def _rpc_76(ctx, params):
    return await ctx.handle_preview_checkpoint(params)

@register('poor-cli/compareFiles')
async def _rpc_77(ctx, params):
    return await ctx.handle_compare_files(params)
