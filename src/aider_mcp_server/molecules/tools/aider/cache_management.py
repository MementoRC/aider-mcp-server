import asyncio
import hashlib
import json
from typing import Any, Dict, List, Optional, Tuple

from aider_mcp_server.atoms.utils.diff_cache import DiffCache


class CacheManager:
    """
    Manages a DiffCache instance for diff caching, key generation, and statistics.
    Provides async initialization, shutdown, and main cache processing logic.
    """

    def __init__(self) -> None:
        """
        Initialize the CacheManager with no active DiffCache.
        """
        self._diff_cache: Optional[DiffCache] = None
        self._lock = asyncio.Lock()

    @property
    def diff_cache(self) -> Optional[DiffCache]:
        """
        Property to access the internal DiffCache instance.
        """
        return self._diff_cache

    async def initialize_cache(self) -> None:
        """
        Initialize the DiffCache instance if not already initialized.
        """
        async with self._lock:
            if self._diff_cache is None:
                self._diff_cache = DiffCache()
                await self._diff_cache.start()

    async def shutdown_cache(self) -> None:
        """
        Shutdown and cleanup the DiffCache instance.
        """
        async with self._lock:
            if self._diff_cache is not None:
                await self._diff_cache.shutdown()
                self._diff_cache = None

    def generate_cache_key(self, working_dir: Optional[str], files: List[str]) -> str:
        """
        Generate a unique cache key based on the working directory and file list.

        Args:
            working_dir: The working directory path.
            files: List of file paths.

        Returns:
            A unique string key for the cache.
        """
        # Use a stable, sorted representation for the file list
        files_sorted = sorted(files)
        key_data = {
            "working_dir": working_dir or "",
            "files": files_sorted,
        }
        key_json = json.dumps(key_data, sort_keys=True)
        key_hash = hashlib.sha256(key_json.encode("utf-8")).hexdigest()
        return f"diffcache:{key_hash}"

    async def process_diff_cache(
        self,
        cache_key: str,
        raw_diff_output: str,
        use_diff_cache: bool = True,
        clear_cached_for_unchanged: bool = True,
    ) -> Tuple[str, bool]:
        """
        Handle diff cache processing: compare, update, and return the diff content.

        Args:
            cache_key: The cache key for this diff.
            raw_diff_output: The raw diff string to cache or compare.
            use_diff_cache: Whether to use the diff cache.
            clear_cached_for_unchanged: If True, clear cache if no changes.

        Returns:
            (final_diff_content, is_cached_diff)
        """
        if not use_diff_cache or self._diff_cache is None:
            # No cache: always return the raw diff, not cached
            return raw_diff_output, False

        # Try to load the previous diff from cache and compare
        try:
            # Convert the diff string to a dict for caching (use as-is if not JSON)
            try:
                new_diff = json.loads(raw_diff_output)
            except Exception:
                # If not JSON, store as a string
                new_diff = {"diff": raw_diff_output}

            # Compare and update cache, get only the changes
            changes = await self._diff_cache.compare_and_cache(
                cache_key,
                new_diff,
                clear_cached_for_unchanged=clear_cached_for_unchanged,
            )

            # If there are no changes, return the cached diff (if any)
            if not changes:
                # Try to get the cached diff (should be None if just cleared)
                cached = await self._diff_cache.get(cache_key)
                if cached is not None:
                    # Return the cached diff as string (convert to JSON if dict)
                    cached_str = json.dumps(cached) if isinstance(cached, dict) else str(cached)
                    return cached_str, True
                else:
                    # No cached diff, return empty string
                    return "", True
            else:
                # There are changes, return the new diff (as string)
                changes_str = json.dumps(changes) if isinstance(changes, dict) else str(changes)
                return changes_str, False

        except Exception:
            # On any error, fallback to returning the raw diff and mark as not cached
            # (Do not let cache errors break the main flow)
            return raw_diff_output, False

    def get_cache_statistics(self) -> Dict[str, Any]:
        """
        Get statistics from the DiffCache.

        Returns:
            Dictionary of cache statistics, or empty dict if cache is not initialized.
        """
        if self._diff_cache is not None:
            return self._diff_cache.get_stats()
        return {}
