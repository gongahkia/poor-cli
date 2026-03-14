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
import subprocess
import time
from urllib.parse import unquote, urlparse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# Approximate tokens per character (conservative estimate)
CHARS_PER_TOKEN = 4

# Default context limits
DEFAULT_MAX_TOKENS = 8000
DEFAULT_MAX_FILES = 12
DEFAULT_MAX_FILE_SIZE = 50000  # 50KB per file
DEFAULT_EXPLICIT_MAX_CHARS = 12000
DEFAULT_EXCERPT_MAX_CHARS = 5000
DEFAULT_HEADER_LINES = 40
DEFAULT_EXCERPT_CONTEXT_LINES = 3
DEFAULT_EXCERPT_MATCHES = 3
_STOP_WORDS = {
    "about", "after", "again", "agent", "also", "build", "change", "changes", "check",
    "code", "current", "file", "files", "from", "into", "make", "need", "only", "please",
    "review", "show", "that", "this", "those", "update", "with", "without", "would",
}


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
    source: str = "direct"
    include_full_content: bool = False
    selection_reason: str = ""
    
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
        cache_ttl: int = 60,  # seconds
        lsp_client: Any = None,
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
        self._lsp_client = lsp_client
        
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

    async def select_context_files(
        self,
        message: str,
        explicit_files: Optional[List[str]] = None,
        pinned_files: Optional[List[str]] = None,
        repo_root: Optional[str] = None,
        max_files: Optional[int] = None,
    ) -> ContextResult:
        """Select context files for a chat turn using backend-owned priorities."""
        root = Path(repo_root or Path.cwd()).resolve()
        files_to_include: List[FileContext] = []
        seen_paths: Set[str] = set()
        effective_max_files = max_files or self.max_files

        explicit_files = explicit_files or []
        pinned_files = pinned_files or []

        async def _add_candidates(
            candidates: List[str],
            *,
            source: str,
            base_priority: float,
            include_full_content: bool,
            reason: str,
        ) -> None:
            for file_path in candidates:
                file_ctx = await self._load_file(file_path)
                if not file_ctx or file_ctx.path in seen_paths:
                    continue
                file_ctx.source = source
                file_ctx.include_full_content = include_full_content
                file_ctx.selection_reason = reason
                file_ctx.priority = base_priority
                files_to_include.append(file_ctx)
                seen_paths.add(file_ctx.path)

        await _add_candidates(
            self._normalize_input_paths(explicit_files),
            source="explicit",
            base_priority=400.0,
            include_full_content=True,
            reason="explicit path reference",
        )
        await _add_candidates(
            self._normalize_input_paths(pinned_files),
            source="pinned",
            base_priority=300.0,
            include_full_content=False,
            reason="pinned context file",
        )
        await _add_candidates(
            self._discover_git_changed_files(root),
            source="git",
            base_priority=200.0,
            include_full_content=False,
            reason="git-changed file",
        )
        await _add_candidates(
            self._discover_auto_files(root),
            source="auto",
            base_priority=100.0,
            include_full_content=False,
            reason="workspace auto-selection",
        )

        self._apply_recency_boost(files_to_include)
        files_to_include.sort(key=lambda f: (-f.priority, f.path))

        limited_files = files_to_include[:effective_max_files]
        total_tokens = sum(self._estimate_prompt_tokens(file_ctx, message) for file_ctx in limited_files)
        truncated = len(files_to_include) > len(limited_files)
        source_counts: Dict[str, int] = {}
        for file_ctx in limited_files:
            source_counts[file_ctx.source] = source_counts.get(file_ctx.source, 0) + 1
        source_summary = ", ".join(f"{name}={count}" for name, count in sorted(source_counts.items()))
        message_text = f"Selected {len(limited_files)} files (~{total_tokens} tokens)"
        if source_summary:
            message_text += f" [{source_summary}]"
        if truncated:
            message_text += " [truncated]"

        return ContextResult(
            files=limited_files,
            total_tokens=total_tokens,
            truncated=truncated,
            message=message_text,
        )

    async def build_context_message(
        self,
        message: str,
        selection: ContextResult,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Render a prompt with excerpt-based context sections."""
        if not selection.files:
            return message

        keywords = self._extract_keywords(message)
        sections: List[str] = []
        total_tokens = 0
        truncated = selection.truncated
        token_budget = max_tokens or self.max_tokens

        for file_ctx in selection.files:
            rendered = self._render_context_file(file_ctx, keywords)
            if not rendered:
                continue

            estimated_tokens = max(1, len(rendered) // CHARS_PER_TOKEN)
            if total_tokens + estimated_tokens > token_budget:
                remaining_tokens = token_budget - total_tokens
                if remaining_tokens <= 0:
                    truncated = True
                    break
                rendered = rendered[: remaining_tokens * CHARS_PER_TOKEN] + "\n... (truncated)"
                estimated_tokens = max(1, len(rendered) // CHARS_PER_TOKEN)
                truncated = True

            sections.append(rendered)
            total_tokens += estimated_tokens

        if not sections:
            return message

        header = "## Context Files\n"
        if truncated:
            header += "[excerpted/truncated to fit context budget]\n\n"
        rendered_sections = "\n\n".join(sections)
        return f"{header}{rendered_sections}\n\nUser request: {message}"

    async def preview_context(
        self,
        message: str,
        explicit_files: Optional[List[str]] = None,
        pinned_files: Optional[List[str]] = None,
        repo_root: Optional[str] = None,
        max_tokens: Optional[int] = None,
        max_files: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Return preview metadata for backend-owned context selection."""
        token_budget = max_tokens or self.max_tokens
        selection = await self.select_context_files(
            message=message,
            explicit_files=explicit_files,
            pinned_files=pinned_files,
            repo_root=repo_root,
            max_files=max_files,
        )
        keywords = self._extract_keywords(message)
        files_payload = []
        total_tokens = 0
        truncated = selection.truncated
        for file_ctx in selection.files:
            estimated_tokens = self._estimate_prompt_tokens(file_ctx, message)
            if total_tokens + estimated_tokens > token_budget:
                truncated = True
                break
            files_payload.append(
                {
                    "path": file_ctx.path,
                    "source": file_ctx.source,
                    "estimatedTokens": estimated_tokens,
                    "language": file_ctx.language,
                    "reason": file_ctx.selection_reason,
                    "includeFullContent": file_ctx.include_full_content,
                }
            )
            total_tokens += estimated_tokens
        return {
            "files": files_payload,
            "totalTokens": total_tokens,
            "truncated": truncated,
            "message": selection.message,
            "keywords": keywords[:10],
        }
    
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

        if self._lsp_client is not None and getattr(self._lsp_client, "available", False):
            lsp_files: Dict[str, FileContext] = {}
            try:
                symbols = await self._lsp_client.get_symbols(file_ctx.path)
                for symbol in symbols or []:
                    sel_range = symbol.get("selectionRange") or symbol.get("range") or {}
                    start = sel_range.get("start", {})
                    line = int(start.get("line", 0))
                    character = int(start.get("character", 0))
                    definition = await self._lsp_client.get_definition(
                        file_ctx.path,
                        line,
                        character,
                    )
                    if not definition:
                        continue
                    uri = definition.get("uri")
                    if not uri:
                        continue
                    parsed = urlparse(uri)
                    if parsed.scheme != "file":
                        continue
                    resolved_path = unquote(parsed.path)
                    if not resolved_path:
                        continue
                    imported_file = await self._load_file(resolved_path)
                    if imported_file:
                        lsp_files[imported_file.path] = imported_file
                if lsp_files:
                    return list(lsp_files.values())
            except Exception as e:
                logger.debug(f"LSP import resolution failed; falling back to regex imports: {e}")

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

    def _normalize_input_paths(self, paths: List[str]) -> List[str]:
        normalized: List[str] = []
        seen: Set[str] = set()
        for file_path in paths:
            resolved = str(Path(file_path).expanduser().resolve())
            if resolved not in seen:
                seen.add(resolved)
                normalized.append(resolved)
        return normalized

    def _discover_git_changed_files(self, repo_root: Path) -> List[str]:
        try:
            result = subprocess.run(
                ["git", "-C", str(repo_root), "status", "--porcelain", "--untracked-files=all"],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except Exception:
            return []

        if result.returncode != 0:
            return []

        changed: List[str] = []
        seen: Set[str] = set()
        for raw_line in result.stdout.splitlines():
            if len(raw_line) < 4:
                continue
            rel_path = raw_line[3:].strip()
            if " -> " in rel_path:
                rel_path = rel_path.split(" -> ", maxsplit=1)[-1].strip()
            if not rel_path:
                continue
            candidate = (repo_root / rel_path).resolve()
            if not candidate.is_file():
                continue
            path_parts = set(candidate.parts)
            if ".git" in path_parts or ".poor-cli" in path_parts:
                continue
            resolved = str(candidate)
            if resolved not in seen:
                seen.add(resolved)
                changed.append(resolved)
        return changed

    def _discover_auto_files(self, repo_root: Path) -> List[str]:
        candidates: List[Tuple[int, str]] = []
        skipped_dirs = {
            ".git",
            ".poor-cli",
            "node_modules",
            "target",
            "dist",
            "build",
            "__pycache__",
            ".venv",
            "venv",
        }

        discovered = 0
        for root, dirnames, filenames in os.walk(repo_root):
            dirnames[:] = [name for name in sorted(dirnames) if name not in skipped_dirs]
            for filename in sorted(filenames):
                path = Path(root) / filename
                discovered += 1
                if discovered > 5000:
                    break
                if not path.is_file():
                    continue
                if self._is_binary(str(path)):
                    continue
                candidates.append((self._context_relevance_score(path), str(path.resolve())))
            if discovered > 5000:
                break

        candidates.sort(key=lambda item: (-item[0], item[1]))
        return [path for _, path in candidates[: max(self.max_files * 3, 24)]]

    @staticmethod
    def _context_relevance_score(path: Path) -> int:
        file_name = path.name.lower()
        extension = path.suffix.lower()

        score = {
            ".rs": 120,
            ".py": 120,
            ".ts": 120,
            ".tsx": 120,
            ".js": 120,
            ".jsx": 120,
            ".go": 120,
            ".java": 120,
            ".kt": 120,
            ".toml": 80,
            ".yaml": 80,
            ".yml": 80,
            ".json": 80,
            ".md": 60,
            ".sh": 70,
        }.get(extension, 40)

        if file_name in {
            "readme.md",
            "cargo.toml",
            "pyproject.toml",
            "package.json",
            "makefile",
            "main.rs",
            "main.py",
            "app.py",
            "index.ts",
            "index.js",
        }:
            score += 120
        if "test" in file_name:
            score += 40
        if "config" in file_name or file_name.endswith(".env"):
            score += 30
        if file_name.endswith(".lock"):
            score -= 40
        return score

    @staticmethod
    def _extract_keywords(message: str) -> List[str]:
        keywords: List[str] = []
        seen: Set[str] = set()
        for raw_word in re.findall(r"[A-Za-z_][A-Za-z0-9_./-]{2,}", message.lower()):
            word = raw_word.strip(".,:;()[]{}<>\"'")
            if len(word) < 3 or word in _STOP_WORDS:
                continue
            if word not in seen:
                seen.add(word)
                keywords.append(word)
        return keywords[:12]

    def _estimate_prompt_tokens(self, file_ctx: FileContext, message: str) -> int:
        rendered = self._render_context_file(file_ctx, self._extract_keywords(message))
        if not rendered:
            return 0
        return max(1, len(rendered) // CHARS_PER_TOKEN)

    @staticmethod
    def _line_window(content: str, start: int, end: int) -> str:
        lines = content.splitlines()
        start_idx = max(0, start)
        end_idx = min(len(lines), end)
        return "\n".join(lines[start_idx:end_idx]).strip()

    def _render_context_file(self, file_ctx: FileContext, keywords: List[str]) -> str:
        content = file_ctx.content
        if file_ctx.include_full_content:
            excerpt = content[:DEFAULT_EXPLICIT_MAX_CHARS]
            if len(content) > DEFAULT_EXPLICIT_MAX_CHARS:
                excerpt += "\n... (truncated explicit file)"
        else:
            excerpt = self._build_excerpt_content(file_ctx, keywords)

        if not excerpt.strip():
            return ""

        return (
            f"### {file_ctx.path} [{file_ctx.source}]\n"
            f"```{file_ctx.language}\n{excerpt}\n```"
        )

    def _build_excerpt_content(self, file_ctx: FileContext, keywords: List[str]) -> str:
        sections: List[str] = []
        seen_chunks: Set[str] = set()
        content = file_ctx.content
        lines = content.splitlines()

        header = "\n".join(lines[:DEFAULT_HEADER_LINES]).strip()
        if header:
            seen_chunks.add(header)
            sections.append(header)

        import_block = self._extract_import_block(lines, file_ctx.language)
        if import_block and import_block not in seen_chunks:
            seen_chunks.add(import_block)
            sections.append(import_block)

        lowered_lines = [line.lower() for line in lines]
        matches = 0
        for keyword in keywords:
            if matches >= DEFAULT_EXCERPT_MATCHES:
                break
            for idx, line in enumerate(lowered_lines):
                if keyword in line:
                    chunk = self._line_window(
                        content,
                        idx - DEFAULT_EXCERPT_CONTEXT_LINES,
                        idx + DEFAULT_EXCERPT_CONTEXT_LINES + 1,
                    )
                    if chunk and chunk not in seen_chunks:
                        seen_chunks.add(chunk)
                        sections.append(chunk)
                        matches += 1
                    break

        rendered = "\n\n...\n\n".join(section for section in sections if section).strip()
        if len(rendered) > DEFAULT_EXCERPT_MAX_CHARS:
            rendered = rendered[:DEFAULT_EXCERPT_MAX_CHARS] + "\n... (excerpt truncated)"
        return rendered

    def _extract_import_block(self, lines: List[str], language: str) -> str:
        if language not in self._import_patterns:
            return ""

        collected: List[str] = []
        for line in lines[:120]:
            stripped = line.strip()
            if not stripped and not collected:
                continue
            if any(re.search(pattern, line) for pattern in self._import_patterns[language]):
                collected.append(line)
                continue
            if collected:
                break

        return "\n".join(collected).strip()
    
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
