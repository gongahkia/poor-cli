# src/utils.py

import os
import hashlib
import unicodedata

# Grammar cache for incremental parsing
_grammar_cache = {}  # file_path -> (mtime, hash, grammar)


def normalize_unicode(text, form='NFC'):
    """Normalize Unicode text to specified form (NFC, NFD, NFKC, NFKD)."""
    return unicodedata.normalize(form, text)


def _get_file_hash(content):
    """Calculate hash of file content for change detection."""
    return hashlib.md5(content.encode('utf-8')).hexdigest()


def _is_cache_valid(file_path):
    """Check if cached grammar is still valid."""
    if file_path not in _grammar_cache:
        return False
    cached_mtime, cached_hash, _ = _grammar_cache[file_path]
    try:
        current_mtime = os.path.getmtime(file_path)
        if current_mtime != cached_mtime:
            return False
        return True
    except OSError:
        return False


def clear_grammar_cache(file_path=None):
    """Clear grammar cache. If file_path provided, only clear that entry."""
    global _grammar_cache
    if file_path:
        _grammar_cache.pop(file_path, None)
    else:
        _grammar_cache.clear()


def get_grammar_cache():
    """Get reference to the grammar cache."""
    return _grammar_cache


def set_grammar_cache(file_path, mtime, file_hash, grammar):
    """Set a grammar cache entry."""
    _grammar_cache[file_path] = (mtime, file_hash, grammar)
