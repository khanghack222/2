"""
Cache Service - TTL-based caching with LRU eviction
Pattern: Service layer with configurable TTL
"""
import time
from typing import Any, Optional, Dict
from collections import OrderedDict
import asyncio


class CacheService:
    """
    In-memory cache with TTL and LRU eviction.
    Thread-safe for async operations.
    """

    def __init__(self, max_size: int = 1000, default_ttl: float = 300.0):
        """
        Initialize cache.

        Args:
            max_size: Maximum number of items
            default_ttl: Default TTL in seconds
        """
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._cache: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found/expired
        """
        async with self._lock:
            if key not in self._cache:
                return None

            value, expire_time = self._cache[key]

            # Check if expired
            if time.time() > expire_time:
                del self._cache[key]
                return None

            # Move to end (most recently used)
            self._cache.move_to_end(key)
            return value

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[float] = None
    ) -> None:
        """
        Set value in cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: TTL in seconds (uses default if None)
        """
        if ttl is None:
            ttl = self.default_ttl

        expire_time = time.time() + ttl

        async with self._lock:
            # Remove if exists (to update position)
            if key in self._cache:
                del self._cache[key]

            # Add to end
            self._cache[key] = (value, expire_time)

            # Evict oldest if over size limit
            while len(self._cache) > self.max_size:
                self._cache.popitem(last=False)

    async def delete(self, key: str) -> bool:
        """
        Delete value from cache.

        Args:
            key: Cache key

        Returns:
            True if deleted
        """
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    async def clear(self) -> None:
        """Clear all cached values"""
        async with self._lock:
            self._cache.clear()

    async def cleanup_expired(self) -> int:
        """
        Remove all expired entries.

        Returns:
            Number of entries removed
        """
        async with self._lock:
            now = time.time()
            expired = [
                key for key, (_, expire_time) in self._cache.items()
                if now > expire_time
            ]

            for key in expired:
                del self._cache[key]

            return len(expired)

    async def size(self) -> int:
        """Get current cache size"""
        return len(self._cache)

    async def stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        return {
            "size": len(self._cache),
            "max_size": self.max_size,
            "default_ttl": self.default_ttl,
        }
