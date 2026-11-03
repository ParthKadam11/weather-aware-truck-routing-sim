"""Simple TTL cache (in-memory). Swap for Redis later via the same interface."""

from __future__ import annotations

import threading
import time
from typing import Any, Hashable


class TtlCache:
    """Thread-safe in-memory cache with per-key TTL."""

    def __init__(self, default_ttl_s: float = 600.0) -> None:
        self.default_ttl_s = default_ttl_s
        self._store: dict[Hashable, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: Hashable) -> Any | None:
        with self._lock:
            item = self._store.get(key)
            if item is None:
                return None
            expires_at, value = item
            if time.monotonic() >= expires_at:
                del self._store[key]
                return None
            return value

    def set(self, key: Hashable, value: Any, ttl_s: float | None = None) -> None:
        ttl = self.default_ttl_s if ttl_s is None else ttl_s
        with self._lock:
            self._store[key] = (time.monotonic() + ttl, value)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


# Process-wide weather cache used by providers
weather_cache = TtlCache(default_ttl_s=900.0)
