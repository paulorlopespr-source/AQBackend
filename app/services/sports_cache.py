from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable


@dataclass
class CacheEntry:
    value: dict
    created_at: float
    expires_at: float


class SportsCache:
    """Small in-memory cache to reduce repeated API-Sports quota usage.

    It is process-local by design: Railway restarts clear it safely. The cache
    also keeps stale data for a short fallback window so temporary provider
    errors do not necessarily make the Android app empty.
    """

    _entries: dict[str, CacheEntry] = {}
    _locks: dict[str, asyncio.Lock] = {}
    _hits: int = 0
    _misses: int = 0
    _stale_served: int = 0

    @classmethod
    def _lock(cls, key: str) -> asyncio.Lock:
        lock = cls._locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            cls._locks[key] = lock
        return lock

    @classmethod
    def make_key(cls, path: str, params: dict[str, Any]) -> str:
        serialized = "&".join(f"{k}={params[k]}" for k in sorted(params))
        return f"{path}?{serialized}"

    @classmethod
    async def get_or_fetch(
        cls,
        *,
        key: str,
        ttl_seconds: int,
        stale_seconds: int,
        fetcher: Callable[[], Awaitable[dict]],
        force_refresh: bool = False,
    ) -> tuple[dict, str]:
        now = time.monotonic()
        entry = cls._entries.get(key)
        if not force_refresh and entry and now < entry.expires_at:
            cls._hits += 1
            return entry.value, "HIT"

        async with cls._lock(key):
            now = time.monotonic()
            entry = cls._entries.get(key)
            if not force_refresh and entry and now < entry.expires_at:
                cls._hits += 1
                return entry.value, "HIT"

            cls._misses += 1
            try:
                value = await fetcher()
            except Exception:
                if entry and now < entry.expires_at + stale_seconds:
                    cls._stale_served += 1
                    return entry.value, "STALE"
                raise

            cls._entries[key] = CacheEntry(
                value=value,
                created_at=now,
                expires_at=now + max(1, ttl_seconds),
            )
            return value, "MISS"

    @classmethod
    def clear(cls) -> int:
        total = len(cls._entries)
        cls._entries.clear()
        cls._locks.clear()
        return total

    @classmethod
    def stats(cls) -> dict[str, int]:
        now = time.monotonic()
        fresh = sum(1 for item in cls._entries.values() if now < item.expires_at)
        return {
            "entries": len(cls._entries),
            "fresh_entries": fresh,
            "hits": cls._hits,
            "misses": cls._misses,
            "stale_served": cls._stale_served,
        }
