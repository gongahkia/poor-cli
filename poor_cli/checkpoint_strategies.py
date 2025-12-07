"""
Advanced Checkpoint Strategies for poor-cli

Implements sophisticated checkpoint strategies:
- Project-aware checkpointing (detect project type, ignore appropriate files)
- Partial checkpoints (selective file tracking)
- Advanced compression strategies
- Smart deduplication
- Incremental checkpoints
"""

import os
import json
import zlib
import lzma
from pathlib import Path
from typing import List, Dict, Set, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
import re

from poor_cli.checkpoint import CheckpointManager, Checkpoint, FileSnapshot
from poor_cli.exceptions import setup_logger

logger = setup_logger(__name__)


class ProjectType(Enum):
    """Detected project type"""
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    RUST = "rust"
    GO = "go"
    JAVA = "java"
    WEB = "web"
    UNKNOWN = "unknown"


class CompressionStrategy(Enum):
    """Compression strategy options"""
    NONE = "none"
    ZLIB_FAST = "zlib_fast"  # level 1
    ZLIB_DEFAULT = "zlib_default"  # level 6
    ZLIB_MAX = "zlib_max"  # level 9
    LZMA = "lzma"  # Best compression, slower


@dataclass
class ProjectIgnoreRules:
    """Rules for ignoring files in a project"""
    patterns: List[str] = field(default_factory=list)
    directories: Set[str] = field(default_factory=set)
    extensions: Set[str] = field(default_factory=set)


class ProjectDetector:
    """Detects project type and provides appropriate ignore rules"""

    # Default ignore patterns for each project type
    IGNORE_RULES = {
        ProjectType.PYTHON: ProjectIgnoreRules(
            patterns=[
                r"__pycache__/.*",
                r"\.pyc$",
                r"\.pyo$",
                r"\.egg-info/.*",
                r"\.pytest_cache/.*",
                r"\.tox/.*",
                r"\.mypy_cache/.*",
                r"\.venv/.*",
                r"venv/.*",
                r"env/.*",
                r"dist/.*",
                r"build/.*",
            ],
            directories={
                "__pycache__", ".pytest_cache", ".mypy_cache",
                ".tox", "venv", "env", ".venv", "dist", "build"
            },
            extensions={".pyc", ".pyo"}
        ),
        ProjectType.JAVASCRIPT: ProjectIgnoreRules(
            patterns=[
                r"node_modules/.*",
                r"\.npm/.*",
                r"dist/.*",
                r"build/.*",
                r"coverage/.*",
                r"\.next/.*",
                r"\.nuxt/.*",
            ],
            directories={
                "node_modules", "dist", "build", "coverage",
                ".next", ".nuxt", ".cache"
            },
            extensions={".min.js", ".min.css"}
        ),
        ProjectType.TYPESCRIPT: ProjectIgnoreRules(
            patterns=[
                r"node_modules/.*",
                r"dist/.*",
                r"build/.*",
                r"\.tsbuildinfo$",
            ],
            directories={
                "node_modules", "dist", "build", "coverage"
            },
            extensions={".js.map", ".d.ts.map"}
        ),
        ProjectType.RUST: ProjectIgnoreRules(
            patterns=[
                r"target/.*",
                r"Cargo\.lock$",
            ],
            directories={"target"},
            extensions={}
        ),
        ProjectType.GO: ProjectIgnoreRules(
            patterns=[
                r"vendor/.*",
                r"\.go\.mod\.sum$",
            ],
            directories={"vendor", "bin"},
            extensions={}
        ),
        ProjectType.JAVA: ProjectIgnoreRules(
            patterns=[
                r"target/.*",
                r"\.class$",
                r"\.jar$",
                r"\.war$",
            ],
            directories={"target", "build", "out"},
            extensions={".class"}
        ),
    }

    def detect_project_type(self, workspace_root: Path) -> ProjectType:
        """Detect project type from workspace contents

        Args:
            workspace_root: Root directory of workspace

        Returns:
            Detected project type
        """
        # Check for indicator files
        if (workspace_root / "setup.py").exists() or \
           (workspace_root / "pyproject.toml").exists() or \
           (workspace_root / "requirements.txt").exists():
            return ProjectType.PYTHON

        if (workspace_root / "package.json").exists():
            # Check if TypeScript
            if (workspace_root / "tsconfig.json").exists():
                return ProjectType.TYPESCRIPT
            return ProjectType.JAVASCRIPT

        if (workspace_root / "Cargo.toml").exists():
            return ProjectType.RUST

        if (workspace_root / "go.mod").exists():
            return ProjectType.GO

        if (workspace_root / "pom.xml").exists() or \
           (workspace_root / "build.gradle").exists():
            return ProjectType.JAVA

        # Check for web project (HTML/CSS/JS files)
        web_files = list(workspace_root.glob("*.html")) + \
                    list(workspace_root.glob("*.css"))
        if web_files:
            return ProjectType.WEB

        return ProjectType.UNKNOWN

    def get_ignore_rules(self, project_type: ProjectType) -> ProjectIgnoreRules:
        """Get ignore rules for project type"""
        base_rules = self.IGNORE_RULES.get(
            project_type,
            ProjectIgnoreRules()
        )

        # Always ignore common files
        base_rules.patterns.extend([
            r"\.git/.*",
            r"\.DS_Store$",
            r"\.env$",
            r"\.env\.local$",
            r"\.log$",
            r"\.swp$",
            r"\.swo$",
            r"~$",
        ])
        base_rules.directories.update({".git", ".svn", ".hg"})

        return base_rules


class FileFilter:
    """Filters files based on ignore rules"""

    def __init__(self, ignore_rules: ProjectIgnoreRules):
        self.ignore_rules = ignore_rules
        self.pattern_regexes = [
            re.compile(pattern) for pattern in ignore_rules.patterns
        ]

    def should_include(self, file_path: str, workspace_root: Path) -> bool:
        """Determine if file should be included in checkpoint

        Args:
            file_path: Path to file
            workspace_root: Root directory of workspace

        Returns:
            True if file should be included
        """
        path = Path(file_path)

        # Check if absolute path, convert to relative
        try:
            if path.is_absolute():
                path = path.relative_to(workspace_root)
        except ValueError:
            # Path not relative to workspace, include it
            return True

        path_str = str(path)

        # Check if any part of path is in ignored directories
        for part in path.parts:
            if part in self.ignore_rules.directories:
                return False

        # Check extension
        if path.suffix in self.ignore_rules.extensions:
            return False

        # Check patterns
        for regex in self.pattern_regexes:
            if regex.search(path_str):
                return False

        return True


@dataclass
class CompressionResult:
    """Result of compression operation"""
    original_size: int
    compressed_size: int
    strategy: CompressionStrategy
    compression_time: float

    @property
    def ratio(self) -> float:
        """Compression ratio (0-1)"""
        if self.original_size == 0:
            return 0.0
        return 1 - (self.compressed_size / self.original_size)

    @property
    def ratio_percent(self) -> float:
        """Compression ratio as percentage"""
        return self.ratio * 100


class SmartCompressor:
    """Intelligent compression with strategy selection"""

    def __init__(self):
        self.compression_stats: Dict[str, List[CompressionResult]] = {}

    def compress(
        self,
        content: bytes,
        file_ext: str = "",
        strategy: Optional[CompressionStrategy] = None
    ) -> tuple[bytes, CompressionStrategy]:
        """Compress content with smart strategy selection

        Args:
            content: Content to compress
            file_ext: File extension (for strategy selection)
            strategy: Force specific strategy (None = auto-select)

        Returns:
            Tuple of (compressed_content, strategy_used)
        """
        # Auto-select strategy if not specified
        if strategy is None:
            strategy = self._select_strategy(content, file_ext)

        # Compress
        if strategy == CompressionStrategy.NONE:
            return content, strategy

        elif strategy == CompressionStrategy.ZLIB_FAST:
            compressed = zlib.compress(content, level=1)

        elif strategy == CompressionStrategy.ZLIB_DEFAULT:
            compressed = zlib.compress(content, level=6)

        elif strategy == CompressionStrategy.ZLIB_MAX:
            compressed = zlib.compress(content, level=9)

        elif strategy == CompressionStrategy.LZMA:
            compressed = lzma.compress(content, preset=9)

        else:
            compressed = content

        # Only use compression if it actually reduces size
        if len(compressed) < len(content):
            return compressed, strategy
        else:
            return content, CompressionStrategy.NONE

    def decompress(
        self,
        content: bytes,
        strategy: CompressionStrategy
    ) -> bytes:
        """Decompress content

        Args:
            content: Compressed content
            strategy: Compression strategy used

        Returns:
            Decompressed content
        """
        if strategy == CompressionStrategy.NONE:
            return content

        elif strategy in [
            CompressionStrategy.ZLIB_FAST,
            CompressionStrategy.ZLIB_DEFAULT,
            CompressionStrategy.ZLIB_MAX
        ]:
            return zlib.decompress(content)

        elif strategy == CompressionStrategy.LZMA:
            return lzma.decompress(content)

        else:
            return content

    def _select_strategy(self, content: bytes, file_ext: str) -> CompressionStrategy:
        """Select best compression strategy for content

        Args:
            content: Content to compress
            file_ext: File extension

        Returns:
            Selected compression strategy
        """
        size = len(content)

        # Don't compress small files (<1KB)
        if size < 1024:
            return CompressionStrategy.NONE

        # Already compressed formats
        compressed_exts = {
            ".jpg", ".jpeg", ".png", ".gif", ".webp",
            ".mp3", ".mp4", ".avi", ".mov",
            ".zip", ".gz", ".tar", ".7z",
            ".pdf", ".woff", ".woff2"
        }
        if file_ext.lower() in compressed_exts:
            return CompressionStrategy.NONE

        # Large text files - use maximum compression
        if size > 1024 * 1024:  # >1MB
            text_exts = {".txt", ".log", ".json", ".xml", ".csv", ".md"}
            if file_ext.lower() in text_exts:
                return CompressionStrategy.LZMA

        # Medium files - use default compression
        if size > 10 * 1024:  # >10KB
            return CompressionStrategy.ZLIB_DEFAULT

        # Small files - use fast compression
        return CompressionStrategy.ZLIB_FAST


class PartialCheckpointStrategy:
    """Strategy for creating partial checkpoints"""

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.project_detector = ProjectDetector()
        self.project_type = self.project_detector.detect_project_type(workspace_root)
        self.ignore_rules = self.project_detector.get_ignore_rules(self.project_type)
        self.file_filter = FileFilter(self.ignore_rules)

    def filter_files(self, file_paths: List[str]) -> List[str]:
        """Filter file list based on project rules

        Args:
            file_paths: List of file paths

        Returns:
            Filtered list of file paths
        """
        filtered = []
        for file_path in file_paths:
            if self.file_filter.should_include(file_path, self.workspace_root):
                filtered.append(file_path)
            else:
                logger.debug(f"Filtered out: {file_path}")

        logger.info(f"Filtered {len(file_paths)} files to {len(filtered)} files")
        return filtered

    def get_important_files_only(self, file_paths: List[str]) -> List[str]:
        """Get only important source files (no generated/cache files)

        Args:
            file_paths: List of file paths

        Returns:
            List of important file paths
        """
        # First apply normal filtering
        filtered = self.filter_files(file_paths)

        # Then filter to source files only
        source_extensions = {
            ".py", ".js", ".ts", ".jsx", ".tsx",
            ".rs", ".go", ".java", ".c", ".cpp", ".h",
            ".css", ".scss", ".html", ".vue",
            ".yaml", ".yml", ".json", ".toml",
            ".md", ".txt"
        }

        important = []
        for file_path in filtered:
            ext = Path(file_path).suffix.lower()
            if ext in source_extensions:
                important.append(file_path)

        logger.info(f"Selected {len(important)} important files from {len(filtered)}")
        return important


class IncrementalCheckpointStrategy:
    """Strategy for incremental checkpoints (only changed files)"""

    def __init__(self, checkpoint_manager: CheckpointManager):
        self.checkpoint_manager = checkpoint_manager

    def get_changed_files(
        self,
        file_paths: List[str],
        since_checkpoint_id: Optional[str] = None
    ) -> List[str]:
        """Get files that changed since a checkpoint

        Args:
            file_paths: List of file paths to check
            since_checkpoint_id: Checkpoint ID to compare against (None = last)

        Returns:
            List of changed file paths
        """
        # Get reference checkpoint
        if since_checkpoint_id:
            checkpoint = self.checkpoint_manager.get_checkpoint(since_checkpoint_id)
        else:
            checkpoints = self.checkpoint_manager.list_checkpoints(limit=1)
            checkpoint = checkpoints[0] if checkpoints else None

        if not checkpoint:
            # No reference checkpoint, all files are "changed"
            return file_paths

        # Build map of file -> hash from checkpoint
        checkpoint_hashes = {
            snapshot.file_path: snapshot.content_hash
            for snapshot in checkpoint.snapshots
        }

        # Check which files changed
        changed = []
        for file_path in file_paths:
            path = Path(file_path)
            if not path.exists():
                # File was deleted
                if str(path.absolute()) in checkpoint_hashes:
                    changed.append(file_path)
                continue

            # Compute current hash
            try:
                with open(path, 'rb') as f:
                    content = f.read()
                import hashlib
                current_hash = hashlib.sha256(content).hexdigest()[:16]

                # Compare with checkpoint hash
                old_hash = checkpoint_hashes.get(str(path.absolute()))
                if old_hash != current_hash:
                    changed.append(file_path)
            except Exception as e:
                logger.warning(f"Failed to check {file_path}: {e}")
                continue

        logger.info(f"Found {len(changed)} changed files out of {len(file_paths)}")
        return changed


class StrategyCheckpointManager:
    """Checkpoint manager with advanced strategies"""

    def __init__(
        self,
        checkpoint_manager: CheckpointManager,
        enable_project_aware: bool = True,
        enable_smart_compression: bool = True
    ):
        self.checkpoint_manager = checkpoint_manager
        self.enable_project_aware = enable_project_aware
        self.enable_smart_compression = enable_smart_compression

        # Initialize strategies
        self.partial_strategy = PartialCheckpointStrategy(
            checkpoint_manager.workspace_root
        )
        self.incremental_strategy = IncrementalCheckpointStrategy(
            checkpoint_manager
        )
        self.compressor = SmartCompressor()

    def create_smart_checkpoint(
        self,
        file_paths: List[str],
        description: str,
        operation_type: str = "auto",
        partial: bool = False,
        incremental: bool = False,
        important_only: bool = False
    ) -> Checkpoint:
        """Create checkpoint with smart strategies

        Args:
            file_paths: List of file paths
            description: Checkpoint description
            operation_type: Type of operation
            partial: Use partial checkpoint (filter files)
            incremental: Only include changed files
            important_only: Only include important source files

        Returns:
            Created checkpoint
        """
        # Apply strategies
        filtered_paths = file_paths

        if self.enable_project_aware and partial:
            filtered_paths = self.partial_strategy.filter_files(filtered_paths)

        if important_only:
            filtered_paths = self.partial_strategy.get_important_files_only(filtered_paths)

        if incremental:
            filtered_paths = self.incremental_strategy.get_changed_files(filtered_paths)

        if not filtered_paths:
            logger.warning("No files to checkpoint after applying strategies")
            filtered_paths = file_paths  # Fallback to original list

        # Create checkpoint with smart compression
        checkpoint = self.checkpoint_manager.create_checkpoint(
            file_paths=filtered_paths,
            description=description,
            operation_type=operation_type
        )

        # Add strategy metadata
        checkpoint.metadata['strategies'] = {
            'partial': partial,
            'incremental': incremental,
            'important_only': important_only,
            'project_type': self.partial_strategy.project_type.value,
            'original_file_count': len(file_paths),
            'filtered_file_count': len(filtered_paths)
        }

        return checkpoint
