"""Markov-chain tool prefetcher for predictive cache warming."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

_DEFAULT_DIR = Path.home() / ".gathon" / "prefetch"
_TRANSITIONS_FILE = _DEFAULT_DIR / "transitions.json"


def _make_state(tool_name: str, symbol_name: str = "") -> str:
    """Build a state key from tool + optional symbol."""
    if symbol_name:
        return f"{tool_name}:{symbol_name}"
    return tool_name


class MarkovPrefetcher:
    """First-order Markov chain for predicting next MCP tool call."""

    def __init__(self, max_history: int = 200) -> None:
        self._max_history = max_history
        self._transitions: dict[str, dict[str, int]] = {}
        self._current_state: str | None = None
        self._session_count: int = 0
        self.load()

    # -- public API ----------------------------------------------------------

    def record(self, tool_name: str, symbol_name: str = "") -> None:
        """Record a tool invocation and update transition from previous state."""
        state = _make_state(tool_name, symbol_name)

        if self._current_state is not None:
            prev = self._current_state
            if prev not in self._transitions:
                self._transitions[prev] = {}
            self._transitions[prev][state] = (
                self._transitions[prev].get(state, 0) + 1
            )

        self._current_state = state

    def predict(self, top_k: int = 3) -> list[tuple[str, float]]:
        """Predict next tool+symbol pairs with probability.

        Returns list of (state, probability) tuples sorted by probability desc.
        """
        if self._current_state is None:
            return []

        nexts = self._transitions.get(self._current_state)
        if not nexts:
            return []

        total = sum(nexts.values())
        ranked = sorted(nexts.items(), key=lambda kv: kv[1], reverse=True)
        return [(state, count / total) for state, count in ranked[:top_k]]

    def save(self) -> None:
        """Persist transition model to disk."""
        _DEFAULT_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "transitions": self._transitions,
            "session_count": self._session_count,
        }
        _TRANSITIONS_FILE.write_text(json.dumps(payload, indent=2))

    def load(self) -> None:
        """Load transition model from disk if it exists."""
        if not _TRANSITIONS_FILE.exists():
            return
        try:
            payload = json.loads(_TRANSITIONS_FILE.read_text())
            self._transitions = payload.get("transitions", {})
            self._session_count = payload.get("session_count", 0)
        except (json.JSONDecodeError, KeyError):
            self._transitions = {}
            self._session_count = 0

    def stats(self) -> dict:
        """Return summary statistics about the transition model."""
        total_states = len(self._transitions)
        total_transitions = sum(
            sum(nexts.values()) for nexts in self._transitions.values()
        )

        # top 10 most common transitions
        all_edges: list[tuple[str, str, int]] = []
        for src, nexts in self._transitions.items():
            for dst, count in nexts.items():
                all_edges.append((src, dst, count))
        all_edges.sort(key=lambda e: e[2], reverse=True)

        top_transitions = [
            {"from": src, "to": dst, "count": cnt}
            for src, dst, cnt in all_edges[:10]
        ]

        return {
            "total_states": total_states,
            "total_transitions": total_transitions,
            "session_count": self._session_count,
            "top_transitions": top_transitions,
        }

    def reset(self) -> None:
        """Clear all data and remove persisted file."""
        self._transitions = {}
        self._current_state = None
        self._session_count = 0
        if _TRANSITIONS_FILE.exists():
            _TRANSITIONS_FILE.unlink()


class PrefetchCache:
    """In-memory cache for pre-warmed tool results with TTL expiry."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[Any, float]] = {}  # key -> (value, expiry)
        self._hits: int = 0
        self._misses: int = 0

    @staticmethod
    def make_key(tool_name: str, args: dict | None = None) -> str:
        """Build cache key from tool name and args hash."""
        if args:
            args_json = json.dumps(args, sort_keys=True, default=str)
            args_hash = hashlib.sha256(args_json.encode()).hexdigest()[:8]
        else:
            args_hash = "no_args"
        return f"{tool_name}:{args_hash}"

    def put(self, key: str, value: Any, ttl_seconds: int = 300) -> None:
        """Store a value with expiry."""
        self._store[key] = (value, time.monotonic() + ttl_seconds)

    def get(self, key: str) -> Any | None:
        """Return value if present and not expired, else None."""
        entry = self._store.get(key)
        if entry is None:
            self._misses += 1
            return None

        value, expiry = entry
        if time.monotonic() > expiry:
            del self._store[key]
            self._misses += 1
            return None

        self._hits += 1
        return value

    def hits(self) -> int:
        return self._hits

    def misses(self) -> int:
        return self._misses

    def stats(self) -> dict:
        total = self._hits + self._misses
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self._hits / total if total > 0 else 0.0,
            "total_entries": len(self._store),
        }


def prefetch_warmup(
    prefetcher: MarkovPrefetcher,
    cache: PrefetchCache,
    current_tool: str,
    current_symbol: str = "",
) -> list[str]:
    """Get predictions and return predicted tool names for pre-warming.

    Records the current invocation, predicts next tools, and returns
    a list of predicted state strings. Actual pre-warming (executing
    tool calls and populating the cache) happens at the caller level.
    """
    prefetcher.record(current_tool, current_symbol)
    predictions = prefetcher.predict(top_k=3)

    predicted: list[str] = []
    for state, _prob in predictions:
        predicted.append(state)

    return predicted
