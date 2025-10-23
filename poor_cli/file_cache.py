"""
File caching system for poor-cli

Provides LRU cache for file reads to improve performance.
"""

from functools import lru_cache
from typing import Optional, Tuple
from pathlib import Path
from poor_cli.exceptions import FileNotFoundError as PoorFileNotFoundError, setup_logger

logger = setup_logger(__name__)


class FileCache:
    """LRU cache for file reads"""

    def __init__(self, max_size: int = 128):
        """Initialize file cache

        Args:
            max_size: Maximum number of files to cache
        """
        self.max_size = max_size
        self._read_cached = lru_cache(maxsize=max_size)(self._read_file_with_mtime)
        logger.info(f"Initialized file cache with max_size={max_size}")

    def _read_file_with_mtime(self, file_path: str, mtime: float) -> str:
        """Read file content (cached by path + mtime)

        Args:
            file_path: Path to file
            mtime: Modification time (for cache key)

        Returns:
            File content as string

        Note:
            The mtime parameter is used as part of the cache key to
            invalidate cache when file is modified.
        """
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            logger.debug(f"Read file from disk (cache miss): {file_path}")
            return content
        except FileNotFoundError:
            raise PoorFileNotFoundError(f"File not found: {file_path}")
        except Exception as e:
            logger.error(f"Error reading file {file_path}: {e}")
            raise

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

        # Get modification time for cache key
        mtime = path.stat().st_mtime

        # Use cached version if available and not modified
        return self._read_cached(str(path.absolute()), mtime)

    async def read_file_async(self, file_path: str) -> str:
        """Async wrapper for read_file

        Args:
            file_path: Path to file

        Returns:
            File content
        """
        import asyncio
        return await asyncio.to_thread(self.read_file, file_path)

    def invalidate(self, file_path: Optional[str] = None):
        """Invalidate cache for file or all files

        Args:
            file_path: Specific file to invalidate, or None for all
        """
        if file_path is None:
            self._read_cached.cache_clear()
            logger.info("Cleared entire file cache")
        else:
            # Cache is keyed by (path, mtime), so we can't selectively
            # invalidate without knowing mtime. For now, clear all.
            # TODO: Implement selective invalidation if needed
            self._read_cached.cache_clear()
            logger.info(f"Cleared cache (full clear due to {file_path} change)")

    def get_cache_info(self) -> dict:
        """Get cache statistics

        Returns:
            Dict with hits, misses, maxsize, currsize
        """
        info = self._read_cached.cache_info()
        return {
            "hits": info.hits,
            "misses": info.misses,
            "maxsize": info.maxsize,
            "currsize": info.currsize,
            "hit_rate": info.hits / (info.hits + info.misses) if (info.hits + info.misses) > 0 else 0.0
        }


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
