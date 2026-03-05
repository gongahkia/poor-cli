"""
Advanced Checkpoint Strategies for poor-cli.

Implements project-aware filtering, incremental detection, and smart compression
for checkpoint creation.
"""

import hashlib
import zlib
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import re
from typing import Dict, List, Optional, Set, Tuple

from poor_cli.checkpoint import Checkpoint, CheckpointManager
from poor_cli.exceptions import setup_logger

logger = setup_logger(__name__)


class ProjectType(Enum):
    """Detected project type."""

    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    RUST = "rust"
    GO = "go"
    JAVA = "java"
    WEB = "web"
    UNKNOWN = "unknown"


class CompressionStrategy(Enum):
    """Compression strategy options."""

    NONE = "none"
    ZLIB_FAST = "zlib_fast"  # level 1
    ZLIB_DEFAULT = "zlib_default"  # level 6
    ZLIB_MAX = "zlib_max"  # level 9


@dataclass
class ProjectIgnoreRules:
    """Rules for ignoring files in a project."""

    patterns: List[str] = field(default_factory=list)
    directories: Set[str] = field(default_factory=set)
    extensions: Set[str] = field(default_factory=set)


@dataclass
class CompressionResult:
    """Result of compression operation."""

    original_size: int
    compressed_size: int
    strategy: CompressionStrategy
    compression_time: float

    @property
    def ratio(self) -> float:
        """Compression ratio (0-1)."""
        if self.original_size == 0:
            return 0.0
        return 1 - (self.compressed_size / self.original_size)

    @property
    def ratio_percent(self) -> float:
        """Compression ratio as percentage."""
        return self.ratio * 100


class ProjectFileFilter:
    """Project-type detection plus file filtering for checkpoints."""

    IGNORE_RULES: Dict[ProjectType, ProjectIgnoreRules] = {
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
                "__pycache__",
                ".pytest_cache",
                ".mypy_cache",
                ".tox",
                "venv",
                "env",
                ".venv",
                "dist",
                "build",
            },
            extensions={".pyc", ".pyo"},
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
                "node_modules",
                "dist",
                "build",
                "coverage",
                ".next",
                ".nuxt",
                ".cache",
            },
            extensions={".min.js", ".min.css"},
        ),
        ProjectType.TYPESCRIPT: ProjectIgnoreRules(
            patterns=[
                r"node_modules/.*",
                r"dist/.*",
                r"build/.*",
                r"\.tsbuildinfo$",
            ],
            directories={"node_modules", "dist", "build", "coverage"},
            extensions={".js.map", ".d.ts.map"},
        ),
        ProjectType.RUST: ProjectIgnoreRules(
            patterns=[r"target/.*", r"Cargo\.lock$"],
            directories={"target"},
            extensions=set(),
        ),
        ProjectType.GO: ProjectIgnoreRules(
            patterns=[r"vendor/.*", r"\.go\.mod\.sum$"],
            directories={"vendor", "bin"},
            extensions=set(),
        ),
        ProjectType.JAVA: ProjectIgnoreRules(
            patterns=[r"target/.*", r"\.class$", r"\.jar$", r"\.war$"],
            directories={"target", "build", "out"},
            extensions={".class"},
        ),
    }

    _ignore_rules_cache: Dict[ProjectType, ProjectIgnoreRules] = {}

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.project_type = self.detect_project_type(workspace_root)
        self.ignore_rules = self.get_ignore_rules(self.project_type)
        self.pattern_regexes = [re.compile(pattern) for pattern in self.ignore_rules.patterns]

    def detect_project_type(self, workspace_root: Path) -> ProjectType:
        """Detect project type from workspace contents."""
        if (
            (workspace_root / "setup.py").exists()
            or (workspace_root / "pyproject.toml").exists()
            or (workspace_root / "requirements.txt").exists()
        ):
            return ProjectType.PYTHON

        if (workspace_root / "package.json").exists():
            if (workspace_root / "tsconfig.json").exists():
                return ProjectType.TYPESCRIPT
            return ProjectType.JAVASCRIPT

        if (workspace_root / "Cargo.toml").exists():
            return ProjectType.RUST

        if (workspace_root / "go.mod").exists():
            return ProjectType.GO

        if (workspace_root / "pom.xml").exists() or (workspace_root / "build.gradle").exists():
            return ProjectType.JAVA

        web_files = list(workspace_root.glob("*.html")) + list(workspace_root.glob("*.css"))
        if web_files:
            return ProjectType.WEB

        return ProjectType.UNKNOWN

    def get_ignore_rules(self, project_type: ProjectType) -> ProjectIgnoreRules:
        """Get ignore rules for project type (cached)."""
        cached = self._ignore_rules_cache.get(project_type)
        if cached is not None:
            return cached

        base = self.IGNORE_RULES.get(project_type, ProjectIgnoreRules())
        combined = ProjectIgnoreRules(
            patterns=list(base.patterns),
            directories=set(base.directories),
            extensions=set(base.extensions),
        )

        # Always ignore common metadata and generated files.
        combined.patterns.extend(
            [
                r"\.git/.*",
                r"\.DS_Store$",
                r"\.env$",
                r"\.env\.local$",
                r"\.log$",
                r"\.swp$",
                r"\.swo$",
                r"~$",
            ]
        )
        combined.directories.update({".git", ".svn", ".hg"})

        self._ignore_rules_cache[project_type] = combined
        return combined

    def should_include(self, file_path: str) -> bool:
        """Determine if file should be included in checkpoint."""
        path = Path(file_path)

        try:
            if path.is_absolute():
                path = path.relative_to(self.workspace_root)
        except ValueError:
            return True

        path_str = str(path)

        for part in path.parts:
            if part in self.ignore_rules.directories:
                return False

        if path.suffix in self.ignore_rules.extensions:
            return False

        for regex in self.pattern_regexes:
            if regex.search(path_str):
                return False

        return True

    def filter_files(self, file_paths: List[str]) -> List[str]:
        """Filter file list based on project rules."""
        filtered: List[str] = []
        for file_path in file_paths:
            if self.should_include(file_path):
                filtered.append(file_path)
            else:
                logger.debug("Filtered out: %s", file_path)

        logger.info("Filtered %d files to %d files", len(file_paths), len(filtered))
        return filtered

    def get_important_files_only(self, file_paths: List[str]) -> List[str]:
        """Get only important source files (no generated/cache files)."""
        filtered = self.filter_files(file_paths)

        source_extensions = {
            ".py",
            ".js",
            ".ts",
            ".jsx",
            ".tsx",
            ".rs",
            ".go",
            ".java",
            ".c",
            ".cpp",
            ".h",
            ".css",
            ".scss",
            ".html",
            ".vue",
            ".yaml",
            ".yml",
            ".json",
            ".toml",
            ".md",
            ".txt",
        }

        important = [
            file_path
            for file_path in filtered
            if Path(file_path).suffix.lower() in source_extensions
        ]
        logger.info("Selected %d important files from %d", len(important), len(filtered))
        return important


class SmartCheckpointStrategy:
    """Smart compression and incremental-change detection strategy."""

    def __init__(self, checkpoint_manager: CheckpointManager):
        self.checkpoint_manager = checkpoint_manager
        self.compression_stats: Dict[str, List[CompressionResult]] = {}

    def compress(
        self,
        content: bytes,
        file_ext: str = "",
        strategy: Optional[CompressionStrategy] = None,
    ) -> Tuple[bytes, CompressionStrategy]:
        """Compress content with strategy selection."""
        if strategy is None:
            strategy = self._select_strategy(content, file_ext)

        if strategy == CompressionStrategy.NONE:
            return content, strategy
        if strategy == CompressionStrategy.ZLIB_FAST:
            compressed = zlib.compress(content, level=1)
        elif strategy == CompressionStrategy.ZLIB_DEFAULT:
            compressed = zlib.compress(content, level=6)
        elif strategy == CompressionStrategy.ZLIB_MAX:
            compressed = zlib.compress(content, level=9)
        else:
            compressed = content

        if len(compressed) < len(content):
            return compressed, strategy
        return content, CompressionStrategy.NONE

    def decompress(self, content: bytes, strategy: CompressionStrategy) -> bytes:
        """Decompress content."""
        if strategy == CompressionStrategy.NONE:
            return content
        if strategy in {
            CompressionStrategy.ZLIB_FAST,
            CompressionStrategy.ZLIB_DEFAULT,
            CompressionStrategy.ZLIB_MAX,
        }:
            return zlib.decompress(content)
        return content

    def _select_strategy(self, content: bytes, file_ext: str) -> CompressionStrategy:
        size = len(content)
        if size < 1024:
            return CompressionStrategy.NONE

        compressed_exts = {
            ".jpg",
            ".jpeg",
            ".png",
            ".gif",
            ".webp",
            ".mp3",
            ".mp4",
            ".avi",
            ".mov",
            ".zip",
            ".gz",
            ".tar",
            ".7z",
            ".pdf",
            ".woff",
            ".woff2",
        }
        if file_ext.lower() in compressed_exts:
            return CompressionStrategy.NONE

        if size > 10 * 1024:
            return CompressionStrategy.ZLIB_DEFAULT

        return CompressionStrategy.ZLIB_FAST

    def get_changed_files(
        self,
        file_paths: List[str],
        since_checkpoint_id: Optional[str] = None,
    ) -> List[str]:
        """Return files changed since a checkpoint."""
        if since_checkpoint_id:
            checkpoint = self.checkpoint_manager.get_checkpoint(since_checkpoint_id)
        else:
            checkpoints = self.checkpoint_manager.list_checkpoints(limit=1)
            checkpoint = checkpoints[0] if checkpoints else None

        if not checkpoint:
            return file_paths

        checkpoint_hashes = {
            snapshot.file_path: snapshot.content_hash for snapshot in checkpoint.snapshots
        }

        changed: List[str] = []
        for file_path in file_paths:
            path = Path(file_path)
            if not path.exists():
                if str(path.absolute()) in checkpoint_hashes:
                    changed.append(file_path)
                continue

            try:
                with open(path, "rb") as handle:
                    content = handle.read()
                current_hash = hashlib.sha256(content).hexdigest()
                old_hash = checkpoint_hashes.get(str(path.absolute()))
                if old_hash != current_hash:
                    changed.append(file_path)
            except OSError as error:
                logger.warning("Failed to check %s: %s", file_path, error)
                continue

        logger.info("Found %d changed files out of %d", len(changed), len(file_paths))
        return changed


class StrategyCheckpointManager:
    """Checkpoint manager with project-aware and incremental strategies."""

    def __init__(
        self,
        checkpoint_manager: CheckpointManager,
        enable_project_aware: bool = True,
        enable_smart_compression: bool = True,
    ):
        self.checkpoint_manager = checkpoint_manager
        self.enable_project_aware = enable_project_aware
        self.enable_smart_compression = enable_smart_compression

        self.project_filter = ProjectFileFilter(checkpoint_manager.workspace_root)
        self.smart_strategy = SmartCheckpointStrategy(checkpoint_manager)

    def create_smart_checkpoint(
        self,
        file_paths: List[str],
        description: str,
        operation_type: str = "auto",
        partial: bool = False,
        incremental: bool = False,
        important_only: bool = False,
    ) -> Checkpoint:
        """Create checkpoint with filtering and incremental strategies."""
        filtered_paths = file_paths

        if self.enable_project_aware and partial:
            filtered_paths = self.project_filter.filter_files(filtered_paths)

        if important_only:
            filtered_paths = self.project_filter.get_important_files_only(filtered_paths)

        if incremental:
            filtered_paths = self.smart_strategy.get_changed_files(filtered_paths)

        if not filtered_paths:
            logger.warning("No files to checkpoint after applying strategies")
            filtered_paths = file_paths

        checkpoint = self.checkpoint_manager.create_checkpoint(
            file_paths=filtered_paths,
            description=description,
            operation_type=operation_type,
        )

        checkpoint.metadata["strategies"] = {
            "partial": partial,
            "incremental": incremental,
            "important_only": important_only,
            "project_type": self.project_filter.project_type.value,
            "original_file_count": len(file_paths),
            "filtered_file_count": len(filtered_paths),
        }

        return checkpoint
