"""CTP filter result caching with TTL."""

from __future__ import annotations

import hashlib
import shlex
import time

from gathon.cli_token_parse import FilterResult


_DEFAULT_TTL = 300  # 5 minutes


class FilterCache:
    """TTL-based cache for FilterResult objects.

    Maps normalized command strings to FilterResult + expiry_time.
    Deletes expired entries on access.
    """

    def __init__(self, ttl_seconds: int = _DEFAULT_TTL) -> None:
        self._store: dict[str, tuple[FilterResult, float]] = {}
        self._ttl = ttl_seconds
        self._hits = 0
        self._misses = 0

    @staticmethod
    def make_key(cmd: str) -> str:
        """Generate cache key from command string.

        Normalizes command (whitespace, env prefix) before hashing to avoid
        cache misses on trivially equivalent commands.
        """
        try:
            from gathon.cli_token_parse.engine import _strip_env_prefix
            cmd = _strip_env_prefix(cmd)
            cmd = " ".join(shlex.split(cmd))
        except Exception:
            pass

        return hashlib.sha256(cmd.encode()).hexdigest()

    def get(self, cmd: str) -> FilterResult | None:
        """Retrieve cached result if present and not expired.

        Returns None and deletes entry if expired.
        Increments hit/miss counters.
        """
        key = self.make_key(cmd)

        if key not in self._store:
            self._misses += 1
            return None

        result, expiry = self._store[key]
        if time.monotonic() >= expiry:
            del self._store[key]
            self._misses += 1
            return None

        self._hits += 1
        return result

    def put(self, cmd: str, result: FilterResult) -> None:
        """Store result with TTL.

        Only caches on success (exit_code == 0) to avoid caching transient failures.
        """
        if result.exit_code != 0:
            return

        key = self.make_key(cmd)
        expiry = time.monotonic() + self._ttl
        self._store[key] = (result, expiry)

    def invalidate(self) -> None:
        """Clear all cached entries."""
        self._store.clear()

    def stats(self) -> dict[str, int]:
        """Return cache statistics: entries, hits, misses."""
        return {
            "entries": len(self._store),
            "hits": self._hits,
            "misses": self._misses,
        }


_FILTER_CACHE = FilterCache()
