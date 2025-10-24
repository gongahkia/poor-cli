"""
File caching system for poor-cli

Provides LRU cache for file reads with persistence and smart pre-caching.
"""

from functools import lru_cache
from typing import Optional, Tuple, List, Dict, Any
from pathlib import Path
from collections import defaultdict, OrderedDict
import sqlite3
import hashlib
import json
import time
from datetime import datetime
from poor_cli.exceptions import FileNotFoundError as PoorFileNotFoundError, setup_logger

logger = setup_logger(__name__)


class FileCache:
    """LRU cache for file reads with persistence and smart pre-caching"""

    def __init__(
        self,
        max_size: int = 128,
        enable_persistence: bool = True,
        enable_precache: bool = True,
        cache_dir: Optional[Path] = None
    ):
        """Initialize file cache

        Args:
            max_size: Maximum number of files to cache
            enable_persistence: Enable persistent cache across sessions
            enable_precache: Enable smart pre-caching based on access patterns
            cache_dir: Directory for cache storage (defaults to ~/.poor-cli/cache)
        """
        self.max_size = max_size
        self.enable_persistence = enable_persistence
        self.enable_precache = enable_precache

        # In-memory cache
        self._cache: OrderedDict[str, Tuple[str, float, float]] = OrderedDict()  # path -> (content, mtime, access_time)

        # Access pattern tracking
        self._access_count: Dict[str, int] = defaultdict(int)
        self._access_sequence: List[Tuple[str, float]] = []  # (file_path, timestamp)

        # Persistent cache setup
        if enable_persistence:
            self.cache_dir = cache_dir or (Path.home() / ".poor-cli" / "cache")
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = self.cache_dir / "file_cache.db"
            self._init_db()
            self._load_access_patterns()

        logger.info(
            f"Initialized file cache: max_size={max_size}, "
            f"persistence={enable_persistence}, precache={enable_precache}"
        )

    def _init_db(self):
        """Initialize persistent cache database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Access patterns table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS access_patterns (
                    file_path TEXT PRIMARY KEY,
                    access_count INTEGER DEFAULT 0,
                    last_access REAL,
                    avg_access_interval REAL
                )
            """)

            # Cached files metadata
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cached_files (
                    file_path TEXT PRIMARY KEY,
                    content_hash TEXT,
                    mtime REAL,
                    cached_at REAL,
                    size_bytes INTEGER
                )
            """)

            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to initialize cache database: {e}")

    def _load_access_patterns(self):
        """Load access patterns from persistent storage"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("SELECT file_path, access_count FROM access_patterns")
            for row in cursor.fetchall():
                self._access_count[row[0]] = row[1]

            conn.close()
            logger.debug(f"Loaded {len(self._access_count)} access patterns")
        except Exception as e:
            logger.warning(f"Failed to load access patterns: {e}")

    def _save_access_patterns(self):
        """Save access patterns to persistent storage"""
        if not self.enable_persistence:
            return

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            for file_path, count in self._access_count.items():
                cursor.execute("""
                    INSERT OR REPLACE INTO access_patterns
                    (file_path, access_count, last_access)
                    VALUES (?, ?, ?)
                """, (file_path, count, time.time()))

            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to save access patterns: {e}")

    def _read_file_from_disk(self, file_path: str) -> str:
        """Read file content from disk

        Args:
            file_path: Path to file

        Returns:
            File content as string
        """
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            logger.debug(f"Read file from disk: {file_path}")
            return content
        except FileNotFoundError:
            raise PoorFileNotFoundError(f"File not found: {file_path}")
        except Exception as e:
            logger.error(f"Error reading file {file_path}: {e}")
            raise

    def _evict_lru(self):
        """Evict least recently used item from cache"""
        if len(self._cache) >= self.max_size:
            # Remove oldest item (first in OrderedDict)
            evicted_path, _ = self._cache.popitem(last=False)
            logger.debug(f"Evicted from cache: {evicted_path}")

    def read_file(self, file_path: str) -> str:
        """Read file with caching

        Args:
            file_path: Path to file

        Returns:
            File content

        The file is cached based on path and modification time.
        If the file is modified, a new version will be read.
        """
        path = Path(file_path)

        if not path.exists():
            raise PoorFileNotFoundError(f"File not found: {file_path}")

        file_path_abs = str(path.absolute())
        mtime = path.stat().st_mtime
        current_time = time.time()

        # Track access pattern
        self._access_count[file_path_abs] += 1
        self._access_sequence.append((file_path_abs, current_time))

        # Check in-memory cache
        if file_path_abs in self._cache:
            cached_content, cached_mtime, _ = self._cache[file_path_abs]
            if cached_mtime == mtime:
                # Cache hit - move to end (most recently used)
                self._cache.move_to_end(file_path_abs)
                self._cache[file_path_abs] = (cached_content, cached_mtime, current_time)
                logger.debug(f"Cache hit: {file_path_abs}")
                return cached_content

        # Cache miss or stale - read from disk
        content = self._read_file_from_disk(file_path_abs)

        # Evict LRU if cache is full
        self._evict_lru()

        # Add to cache
        self._cache[file_path_abs] = (content, mtime, current_time)

        # Trigger precache if enabled
        if self.enable_precache:
            self._precache_related_files(file_path_abs)

        return content

    async def read_file_async(self, file_path: str) -> str:
        """Async wrapper for read_file

        Args:
            file_path: Path to file

        Returns:
            File content
        """
        import asyncio
        return await asyncio.to_thread(self.read_file, file_path)

    def _precache_related_files(self, file_path: str):
        """Pre-cache files that are likely to be accessed next

        Args:
            file_path: Recently accessed file path
        """
        try:
            # Precache files in the same directory
            path = Path(file_path)
            if not path.parent.exists():
                return

            # Get sibling files (same directory)
            sibling_files = [
                str(f.absolute())
                for f in path.parent.iterdir()
                if f.is_file() and f.suffix in ['.py', '.js', '.ts', '.md', '.txt', '.json']
            ]

            # Sort by access count (most frequently accessed first)
            sibling_files.sort(key=lambda f: self._access_count.get(f, 0), reverse=True)

            # Precache top 3 frequently accessed siblings
            precached_count = 0
            for sibling_path in sibling_files[:3]:
                if sibling_path not in self._cache and len(self._cache) < self.max_size - 1:
                    try:
                        sibling = Path(sibling_path)
                        if sibling.exists():
                            content = self._read_file_from_disk(sibling_path)
                            mtime = sibling.stat().st_mtime
                            self._cache[sibling_path] = (content, mtime, time.time())
                            precached_count += 1
                    except Exception as e:
                        logger.debug(f"Precache failed for {sibling_path}: {e}")

            if precached_count > 0:
                logger.debug(f"Precached {precached_count} related files")

        except Exception as e:
            logger.debug(f"Precaching failed: {e}")

    def warm_cache(self, directory: Optional[str] = None, max_files: int = 20):
        """Warm cache by pre-loading frequently accessed files

        Args:
            directory: Directory to warm cache for (None = all tracked files)
            max_files: Maximum number of files to warm
        """
        try:
            # Get most frequently accessed files
            sorted_files = sorted(
                self._access_count.items(),
                key=lambda x: x[1],
                reverse=True
            )

            # Filter by directory if specified
            if directory:
                dir_abs = str(Path(directory).absolute())
                sorted_files = [
                    (path, count)
                    for path, count in sorted_files
                    if path.startswith(dir_abs)
                ]

            # Warm up to max_files
            warmed_count = 0
            for file_path, _ in sorted_files[:max_files]:
                if file_path not in self._cache:
                    try:
                        path = Path(file_path)
                        if path.exists():
                            content = self._read_file_from_disk(file_path)
                            mtime = path.stat().st_mtime
                            self._cache[file_path] = (content, mtime, time.time())
                            warmed_count += 1

                            if len(self._cache) >= self.max_size:
                                break
                    except Exception as e:
                        logger.debug(f"Failed to warm cache for {file_path}: {e}")

            logger.info(f"Warmed cache with {warmed_count} files")

        except Exception as e:
            logger.error(f"Cache warming failed: {e}")

    def invalidate(self, file_path: Optional[str] = None):
        """Invalidate cache for file or all files

        Args:
            file_path: Specific file to invalidate, or None for all
        """
        if file_path is None:
            self._cache.clear()
            logger.info("Cleared entire file cache")
        else:
            file_path_abs = str(Path(file_path).absolute())
            if file_path_abs in self._cache:
                del self._cache[file_path_abs]
                logger.info(f"Invalidated cache for {file_path}")

    def get_cache_info(self) -> dict:
        """Get cache statistics

        Returns:
            Dict with hits, misses, maxsize, currsize, access patterns
        """
        total_accesses = sum(self._access_count.values())
        hits = sum(1 for _ in self._cache.items())
        misses = total_accesses - hits

        # Get most accessed files
        top_files = sorted(
            self._access_count.items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]

        return {
            "maxsize": self.max_size,
            "currsize": len(self._cache),
            "total_accesses": total_accesses,
            "unique_files_accessed": len(self._access_count),
            "hit_rate": hits / total_accesses if total_accesses > 0 else 0.0,
            "top_accessed_files": [
                {"path": path, "count": count}
                for path, count in top_files
            ]
        }

    def save_and_cleanup(self):
        """Save access patterns and cleanup resources"""
        self._save_access_patterns()
        self._cache.clear()


# Global file cache instance
_file_cache: Optional[FileCache] = None


def get_file_cache(max_size: int = 128) -> FileCache:
    """Get global file cache instance

    Args:
        max_size: Maximum cache size (only used on first call)

    Returns:
        FileCache instance
    """
    global _file_cache
    if _file_cache is None:
        _file_cache = FileCache(max_size=max_size)
    return _file_cache
