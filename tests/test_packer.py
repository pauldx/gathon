"""Tests for context packer and Markov prefetcher."""

from __future__ import annotations

from gathon.packer import ContextCandidate, auto_pack, pack_context, score_candidate
from gathon.prefetch import MarkovPrefetcher, PrefetchCache, prefetch_warmup


class TestPacker:
    def test_score_basic(self):
        c = ContextCandidate(
            name="foo", content="x", token_cost=10,
            relevance=1.0, dep_distance=0, recency_days=0.0,
            access_count=10,
        )
        score = score_candidate(c)
        assert score > 0.5

    def test_score_with_query(self):
        c = ContextCandidate(
            name="user_auth", content="x", token_cost=10,
            relevance=0.5,
        )
        s1 = score_candidate(c, query="")
        s2 = score_candidate(c, query="user auth")
        assert s2 > s1

    def test_pack_empty(self):
        result = pack_context([], 1000)
        assert result.items_packed == 0

    def test_pack_fits_all(self):
        candidates = [
            ContextCandidate(name="a", content="x" * 40, token_cost=10, relevance=0.8),
            ContextCandidate(name="b", content="y" * 40, token_cost=10, relevance=0.6),
        ]
        result = pack_context(candidates, budget_tokens=100)
        assert result.items_packed == 2
        assert result.total_tokens == 20

    def test_pack_budget_limit(self):
        candidates = [
            ContextCandidate(name="big", content="x" * 4000, token_cost=1000, relevance=0.5),
            ContextCandidate(name="small", content="y" * 40, token_cost=10, relevance=0.9),
        ]
        result = pack_context(candidates, budget_tokens=50)
        assert result.items_packed == 1
        assert result.candidates[0].name == "small"

    def test_pack_value_density(self):
        candidates = [
            ContextCandidate(name="expensive", content="x" * 4000, token_cost=500, relevance=0.3),
            ContextCandidate(name="cheap_good", content="y" * 40, token_cost=10, relevance=0.9),
        ]
        result = pack_context(candidates, budget_tokens=510)
        assert result.candidates[0].name == "cheap_good"

    def test_auto_pack(self):
        symbols = [
            {"name": "func_a", "content": "def func_a():\n    pass\n"},
            {"name": "func_b", "content": "def func_b():\n    return 42\n", "relevance": 0.8},
        ]
        result = auto_pack(symbols, budget=1000)
        assert result.items_packed >= 1

    def test_zero_budget(self):
        candidates = [
            ContextCandidate(name="a", content="x", token_cost=10, relevance=0.5),
        ]
        result = pack_context(candidates, budget_tokens=0)
        assert result.items_packed == 0


class TestPrefetcher:
    def test_record_and_predict(self):
        pf = MarkovPrefetcher(max_history=10)
        pf.reset()
        pf._transitions = {}
        pf._current_state = None
        pf.record("Bash")
        pf.record("Edit")
        pf.record("Bash")
        pf.record("Edit")
        pf.record("Bash")
        predictions = pf.predict()
        assert len(predictions) >= 1
        assert predictions[0][0] == "Edit"

    def test_stats(self):
        pf = MarkovPrefetcher()
        pf.reset()
        pf._transitions = {}
        pf._current_state = None
        pf.record("A")
        pf.record("B")
        s = pf.stats()
        assert s["total_states"] >= 1
        assert s["total_transitions"] >= 1

    def test_reset(self):
        pf = MarkovPrefetcher()
        pf.reset()
        assert pf.stats()["total_states"] == 0


class TestPrefetchCache:
    def test_put_and_get(self):
        cache = PrefetchCache()
        cache.put("key1", {"data": "value"}, ttl_seconds=300)
        assert cache.get("key1") == {"data": "value"}

    def test_miss(self):
        cache = PrefetchCache()
        assert cache.get("nonexistent") is None

    def test_stats(self):
        cache = PrefetchCache()
        cache.put("k", "v")
        cache.get("k")
        cache.get("miss")
        s = cache.stats()
        assert s["hits"] == 1
        assert s["misses"] == 1

    def test_make_key(self):
        k1 = PrefetchCache.make_key("tool", {"a": 1})
        k2 = PrefetchCache.make_key("tool", {"a": 1})
        k3 = PrefetchCache.make_key("tool", {"b": 2})
        assert k1 == k2
        assert k1 != k3


class TestPrefetchWarmup:
    def test_warmup_returns_predictions(self):
        pf = MarkovPrefetcher()
        pf.reset()
        pf._transitions = {}
        pf._current_state = None
        cache = PrefetchCache()
        pf.record("Bash")
        pf.record("Edit")
        pf.record("Bash")
        predicted = prefetch_warmup(pf, cache, "Edit")
        assert isinstance(predicted, list)
