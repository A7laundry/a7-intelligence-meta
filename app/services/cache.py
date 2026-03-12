"""Simple in-memory TTL cache for A7 Intelligence services."""

import threading
import time
import logging

logger = logging.getLogger(__name__)


class TTLCache:
    """Thread-safe in-memory cache with per-entry TTL expiration."""

    def __init__(self, default_ttl=300):
        self._cache = {}
        self._lock = threading.Lock()
        self.default_ttl = default_ttl

    def get(self, key):
        """Return cached value if present and not expired, else None."""
        with self._lock:
            entry = self._cache.get(key)
            if entry and time.monotonic() < entry['expires']:
                return entry['value']
            return None

    def set(self, key, value, ttl=None):
        """Store value under key with optional TTL override."""
        with self._lock:
            self._cache[key] = {
                'value': value,
                'expires': time.monotonic() + (ttl or self.default_ttl)
            }

    def delete(self, key):
        """Remove a single key from the cache."""
        with self._lock:
            self._cache.pop(key, None)

    def clear(self):
        """Remove all entries from the cache."""
        with self._lock:
            self._cache.clear()


# Module-level cache instances
dashboard_cache = TTLCache(default_ttl=120)   # 2 min for dashboard data
growth_cache = TTLCache(default_ttl=300)      # 5 min for growth scores
analytics_cache = TTLCache(default_ttl=600)   # 10 min for analytics
