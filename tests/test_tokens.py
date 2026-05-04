"""Tests for gathon.tokens — token budget tracking."""

from gathon.tokens import attach_token_meta, estimate_tokens


class TestEstimateTokens:
    def test_string(self):
        assert estimate_tokens("hello world") >= 1
        assert estimate_tokens("a" * 100) == 25

    def test_int(self):
        assert estimate_tokens(42) == 1

    def test_none(self):
        assert estimate_tokens(None) == 0

    def test_dict(self):
        data = {"name": "foo", "kind": "Function"}
        tokens = estimate_tokens(data)
        assert tokens >= 5

    def test_list(self):
        data = [{"name": "a"}, {"name": "b"}]
        tokens = estimate_tokens(data)
        assert tokens >= 5

    def test_empty_string(self):
        assert estimate_tokens("") == 1


class TestAttachTokenMeta:
    def test_adds_meta_field(self):
        data = {"count": 2, "results": [{"name": "a"}, {"name": "b"}]}
        result = attach_token_meta(data)
        assert "_token_meta" in result
        meta = result["_token_meta"]
        assert meta["estimated_tokens"] > 0
        assert meta["result_count"] == 2
        assert meta["avg_tokens_per_result"] > 0

    def test_uses_nodes_key(self):
        data = {"nodes": [{"qn": "a"}, {"qn": "b"}, {"qn": "c"}]}
        result = attach_token_meta(data)
        assert result["_token_meta"]["result_count"] == 3

    def test_uses_count_fallback(self):
        data = {"count": 5, "data": "something"}
        result = attach_token_meta(data)
        assert result["_token_meta"]["result_count"] == 5

    def test_no_results_key(self):
        data = {"name": "foo", "kind": "bar"}
        result = attach_token_meta(data)
        assert result["_token_meta"]["result_count"] == 0
        assert result["_token_meta"]["avg_tokens_per_result"] > 0

    def test_preserves_original_data(self):
        data = {"count": 1, "results": [{"a": 1}]}
        result = attach_token_meta(data)
        assert result["count"] == 1
        assert result["results"] == [{"a": 1}]
