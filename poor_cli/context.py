"""
PoorCLI Context Manager

This module handles intelligent context gathering for AI prompts:
- Gathering relevant files based on imports/references
- Truncating context to fit token limits
- Prioritizing recently edited files
- Caching file contents
"""

import asyncio
import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# Approximate tokens per character (conservative estimate)
CHARS_PER_TOKEN = 4

# Default context limits
DEFAULT_MAX_TOKENS = 8000
DEFAULT_MAX_FILES = 10
DEFAULT_MAX_FILE_SIZE = 50000  # 50KB per file


@dataclass
class FileContext:
    """Represents a file's context information."""
    path: str
    content: str
    size: int
    modified_time: float
    language: str
    priority: float = 0.0
    tokens_estimate: int = 0
    
    def __post_init__(self):
        self.tokens_estimate = len(self.content) // CHARS_PER_TOKEN


@dataclass
class ContextResult:
    """Result of context gathering."""
    files: List[FileContext]
    total_tokens: int
    truncated: bool
    message: str


class ContextManager:
    """
    Manages context gathering for AI prompts.
    
    Features:
    - Import/reference analysis
    - Token-aware truncation
    - LRU caching for file contents
    - Priority-based file selection
    """
    
    def __init__(
        self,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        max_files: int = DEFAULT_MAX_FILES,
        max_file_size: int = DEFAULT_MAX_FILE_SIZE,
        cache_ttl: int = 60  # seconds
    ):
        """
        Initialize the context manager.
        
        Args:
            max_tokens: Maximum tokens for context
            max_files: Maximum number of files to include
            max_file_size: Maximum size per file in bytes
            cache_ttl: Cache time-to-live in seconds
        """
        self.max_tokens = max_tokens
        self.max_files = max_files
        self.max_file_size = max_file_size
        self.cache_ttl = cache_ttl
        
        # File content cache: path -> (content, timestamp)
        self._cache: Dict[str, Tuple[str, float]] = {}
        
        # Recently edited files (for priority)
        self._recent_edits: Dict[str, float] = {}
        
        # Language-specific import patterns
        self._import_patterns = {
            "python": [
                r'^import\s+(\w+)',
                r'^from\s+(\w+(?:\.\w+)*)\s+import',
            ],
            "javascript": [
                r'import\s+.*\s+from\s+[\'"]([^\'"]+)[\'"]',
                r'require\s*\(\s*[\'"]([^\'"]+)[\'"]\s*\)',
            ],
            "typescript": [
                r'import\s+.*\s+from\s+[\'"]([^\'"]+)[\'"]',
                r'require\s*\(\s*[\'"]([^\'"]+)[\'"]\s*\)',
            ],
            "go": [
                r'import\s+[\'"]([^\'"]+)[\'"]',
                r'import\s+\([^)]*[\'"]([^\'"]+)[\'"]',
            ],
            "rust": [
                r'use\s+([\w:]+)',
                r'mod\s+(\w+)',
            ],
            "java": [
                r'import\s+([\w.]+)',
            ],
            "c": [
                r'#include\s*[<"]([^>"]+)[>"]',
            ],
            "cpp": [
                r'#include\s*[<"]([^>"]+)[>"]',
            ],
        }
    
    def mark_file_edited(self, file_path: str) -> None:
        """
        Mark a file as recently edited for priority boosting.
        
        Args:
            file_path: Path to the edited file
        """
        self._recent_edits[str(Path(file_path).resolve())] = time.time()
    
    def clear_cache(self) -> None:
        """Clear the file content cache."""
        self._cache.clear()
    
    async def gather_context(
        self,
        primary_file: Optional[str] = None,
        additional_files: Optional[List[str]] = None,
        working_directory: Optional[str] = None,
        include_imports: bool = True
    ) -> ContextResult:
        """
        Gather context for an AI prompt.
        
        Args:
            primary_file: Main file being edited (highest priority)
            additional_files: Additional files to include
            working_directory: Working directory for relative imports
            include_imports: Whether to analyze and include imports
        
        Returns:
            ContextResult with gathered files and metadata
        """
        files_to_include: List[FileContext] = []
        seen_paths: Set[str] = set()
        
        # Start with primary file
        if primary_file:
            file_ctx = await self._load_file(primary_file)
            if file_ctx:
                file_ctx.priority = 100.0  # Highest priority
                files_to_include.append(file_ctx)
                seen_paths.add(file_ctx.path)
                
                # Analyze imports if enabled
                if include_imports:
                    import_files = await self._find_import_files(
                        file_ctx,
                        working_directory or os.path.dirname(primary_file)
                    )
                    for imp_file in import_files:
                        if imp_file.path not in seen_paths:
                            imp_file.priority = 50.0  # Import priority
                            files_to_include.append(imp_file)
                            seen_paths.add(imp_file.path)
        
        # Add additional files
        if additional_files:
            for file_path in additional_files:
                if file_path not in seen_paths:
                    file_ctx = await self._load_file(file_path)
                    if file_ctx:
                        file_ctx.priority = 25.0  # Additional file priority
                        files_to_include.append(file_ctx)
                        seen_paths.add(file_ctx.path)
        
        # Apply recency boost
        self._apply_recency_boost(files_to_include)
        
        # Sort by priority (descending)
        files_to_include.sort(key=lambda f: f.priority, reverse=True)
        
        # Truncate to fit token limit
        result = self._truncate_to_limit(files_to_include)
        
        return result
    
    async def _load_file(self, file_path: str) -> Optional[FileContext]:
        """
        Load a file's content, using cache if available.
        
        Args:
            file_path: Path to the file
        
        Returns:
            FileContext or None if file can't be read
        """
        try:
            resolved_path = str(Path(file_path).resolve())
            
            # Check cache
            if resolved_path in self._cache:
                content, cached_time = self._cache[resolved_path]
                if time.time() - cached_time < self.cache_ttl:
                    stat = os.stat(resolved_path)
                    return FileContext(
                        path=resolved_path,
                        content=content,
                        size=len(content),
                        modified_time=stat.st_mtime,
                        language=self._detect_language(resolved_path)
                    )
            
            # Read file
            if not os.path.exists(resolved_path):
                return None
            
            stat = os.stat(resolved_path)
            
            # Skip large files
            if stat.st_size > self.max_file_size:
                logger.debug(f"Skipping large file: {resolved_path}")
                return None
            
            # Skip binary files
            if self._is_binary(resolved_path):
                return None
            
            with open(resolved_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # Cache the content
            self._cache[resolved_path] = (content, time.time())
            
            return FileContext(
                path=resolved_path,
                content=content,
                size=len(content),
                modified_time=stat.st_mtime,
                language=self._detect_language(resolved_path)
            )
            
        except Exception as e:
            logger.debug(f"Failed to load file {file_path}: {e}")
            return None
    
    async def _find_import_files(
        self,
        file_ctx: FileContext,
        working_directory: str
    ) -> List[FileContext]:
        """
        Find files referenced by imports in the given file.
        
        Args:
            file_ctx: The file to analyze
            working_directory: Directory for resolving relative imports
        
        Returns:
            List of FileContext for imported files
        """
        import_files: List[FileContext] = []
        patterns = self._import_patterns.get(file_ctx.language, [])
        
        if not patterns:
            return import_files
        
        for pattern in patterns:
            for match in re.finditer(pattern, file_ctx.content, re.MULTILINE):
                import_name = match.group(1)
                resolved = self._resolve_import(
                    import_name,
                    file_ctx.language,
                    working_directory
                )
                
                if resolved:
                    imported_file = await self._load_file(resolved)
                    if imported_file:
                        import_files.append(imported_file)
        
        return import_files
    
    def _resolve_import(
        self,
        import_name: str,
        language: str,
        working_directory: str
    ) -> Optional[str]:
        """
        Resolve an import name to a file path.
        
        Args:
            import_name: The import name/path
            language: Programming language
            working_directory: Base directory
        
        Returns:
            Resolved file path or None
        """
        try:
            if language == "python":
                # Convert module path to file path
                rel_path = import_name.replace(".", os.sep)
                candidates = [
                    os.path.join(working_directory, rel_path + ".py"),
                    os.path.join(working_directory, rel_path, "__init__.py"),
                ]
            elif language in ("javascript", "typescript"):
                # Handle relative and absolute imports
                if import_name.startswith("."):
                    base = working_directory
                else:
                    return None  # Skip node_modules
                
                candidates = [
                    os.path.join(base, import_name + ".js"),
                    os.path.join(base, import_name + ".ts"),
                    os.path.join(base, import_name + ".tsx"),
                    os.path.join(base, import_name, "index.js"),
                    os.path.join(base, import_name, "index.ts"),
                ]
            else:
                return None
            
            for candidate in candidates:
                if os.path.exists(candidate):
                    return candidate
            
            return None
            
        except Exception:
            return None
    
    def _apply_recency_boost(self, files: List[FileContext]) -> None:
        """
        Apply priority boost to recently edited files.
        
        Args:
            files: List of files to boost
        """
        current_time = time.time()
        
        for file_ctx in files:
            if file_ctx.path in self._recent_edits:
                edit_time = self._recent_edits[file_ctx.path]
                recency = current_time - edit_time
                
                # Boost priority based on recency (max 30s window)
                if recency < 30:
                    boost = 20.0 * (1.0 - recency / 30.0)
                    file_ctx.priority += boost
    
    def _truncate_to_limit(self, files: List[FileContext]) -> ContextResult:
        """
        Truncate file list to fit token limit.
        
        Args:
            files: Sorted list of files (by priority)
        
        Returns:
            ContextResult with truncated files
        """
        included_files: List[FileContext] = []
        total_tokens = 0
        truncated = False
        
        for file_ctx in files:
            if len(included_files) >= self.max_files:
                truncated = True
                break
            
            if total_tokens + file_ctx.tokens_estimate > self.max_tokens:
                # Try to include partial file
                remaining_tokens = self.max_tokens - total_tokens
                if remaining_tokens > 500:  # Worth including partial
                    truncated_content = file_ctx.content[:remaining_tokens * CHARS_PER_TOKEN]
                    file_ctx.content = truncated_content + "\n\n... (truncated)"
                    file_ctx.tokens_estimate = remaining_tokens
                    included_files.append(file_ctx)
                    total_tokens += remaining_tokens
                truncated = True
                break
            
            included_files.append(file_ctx)
            total_tokens += file_ctx.tokens_estimate
        
        message = f"Included {len(included_files)} files (~{total_tokens} tokens)"
        if truncated:
            message += " [truncated]"
        
        return ContextResult(
            files=included_files,
            total_tokens=total_tokens,
            truncated=truncated,
            message=message
        )
    
    def _detect_language(self, file_path: str) -> str:
        """
        Detect programming language from file extension.
        
        Args:
            file_path: Path to the file
        
        Returns:
            Language identifier
        """
        ext_map = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".jsx": "javascript",
            ".go": "go",
            ".rs": "rust",
            ".java": "java",
            ".c": "c",
            ".cpp": "cpp",
            ".cc": "cpp",
            ".h": "c",
            ".hpp": "cpp",
            ".rb": "ruby",
            ".php": "php",
            ".swift": "swift",
            ".kt": "kotlin",
            ".scala": "scala",
            ".lua": "lua",
            ".sh": "bash",
            ".bash": "bash",
            ".zsh": "zsh",
            ".fish": "fish",
            ".sql": "sql",
            ".html": "html",
            ".css": "css",
            ".scss": "scss",
            ".less": "less",
            ".json": "json",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".toml": "toml",
            ".md": "markdown",
            ".txt": "text",
        }
        
        ext = Path(file_path).suffix.lower()
        return ext_map.get(ext, "text")
    
    def _is_binary(self, file_path: str) -> bool:
        """
        Check if a file is binary.
        
        Args:
            file_path: Path to the file
        
        Returns:
            True if file appears to be binary
        """
        binary_extensions = {
            ".pyc", ".pyo", ".so", ".dylib", ".dll", ".exe",
            ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico",
            ".pdf", ".doc", ".docx", ".xls", ".xlsx",
            ".zip", ".tar", ".gz", ".rar", ".7z",
            ".wasm", ".o", ".a", ".lib",
        }
        
        ext = Path(file_path).suffix.lower()
        return ext in binary_extensions
    
    def format_context_for_prompt(
        self,
        context_result: ContextResult,
        include_paths: bool = True
    ) -> str:
        """
        Format gathered context for inclusion in a prompt.
        
        Args:
            context_result: Result from gather_context
            include_paths: Whether to include file paths
        
        Returns:
            Formatted context string
        """
        if not context_result.files:
            return ""
        
        parts = ["## Context Files\n"]
        
        for file_ctx in context_result.files:
            if include_paths:
                parts.append(f"### {file_ctx.path}\n")
            
            parts.append(f"```{file_ctx.language}")
            parts.append(file_ctx.content)
            parts.append("```\n")
        
        return "\n".join(parts)


# Singleton instance for convenience
_context_manager: Optional[ContextManager] = None


def get_context_manager() -> ContextManager:
    """Get or create the singleton ContextManager instance."""
    global _context_manager
    if _context_manager is None:
        _context_manager = ContextManager()
    return _context_manager
