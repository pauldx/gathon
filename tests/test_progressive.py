"""Tests for progressive disclosure in query tools."""

from gathon.schema import UnifiedEdge, UnifiedNode
from gathon.store import UnifiedStore


def _make_store(tmp_path):
    db = tmp_path / "graph.db"
    store = UnifiedStore(str(db))
    nodes = [
        UnifiedNode(
            kind="Function", name="foo",
            qualified_name="a.py::foo", file_path="a.py",
            line_start=1, line_end=10, language="python",
            pipeline="code_graph", label="Process input data",
        ),
        UnifiedNode(
            kind="Function", name="bar",
            qualified_name="a.py::bar", file_path="a.py",
            line_start=12, line_end=20, language="python",
            pipeline="code_graph", label="Handle output",
        ),
        UnifiedNode(
            kind="Section", name="intro",
            qualified_name="doc.md::intro", file_path="doc.md",
            file_type="document", pipeline="gathon_doc",
            label="Introduction to the system",
        ),
    ]
    edges = [
        UnifiedEdge(
            kind="CALLS", source_qualified="a.py::foo",
            target_qualified="a.py::bar", file_path="a.py",
        ),
        UnifiedEdge(
            kind="REFERENCES", source_qualified="doc.md::intro",
            target_qualified="a.py::foo", file_path="doc.md",
        ),
    ]
    for n in nodes:
        store.upsert_unified_node(n)
    for e in edges:
        store.upsert_unified_edge(e)
    store.commit()
    return store


class TestSemanticSearchDisclosure:
    def test_index_mode_compact(self, tmp_path):
        store = _make_store(tmp_path)
        from gathon.tools.query import semantic_search
        result = semantic_search(store, "foo", detail_level="index")
        assert result["detail_level"] == "index"
        if result["count"] > 0:
            item = result["results"][0]
            assert "qualified_name" in item
            assert "kind" in item
            assert "label" not in item
            assert "pipeline" not in item
        store.close()

    def test_full_mode_enriched(self, tmp_path):
        store = _make_store(tmp_path)
        from gathon.tools.query import semantic_search
        result = semantic_search(store, "foo", detail_level="full")
        assert result["detail_level"] == "full"
        if result["count"] > 0:
            item = result["results"][0]
            assert "qualified_name" in item
            assert "label" in item
            assert "pipeline" in item
            assert "file_type" in item
        store.close()

    def test_default_is_index(self, tmp_path):
        store = _make_store(tmp_path)
        from gathon.tools.query import semantic_search
        result = semantic_search(store, "foo")
        assert result["detail_level"] == "index"
        store.close()


class TestQueryGraphDisclosure:
    def test_index_mode(self, tmp_path):
        store = _make_store(tmp_path)
        from gathon.tools.query import query_graph
        result = query_graph(store, "a.py::bar", "callers_of")
        assert result["detail_level"] == "index"
        if result["count"] > 0:
            item = result["results"][0]
            assert "kind" in item
            assert "source" in item
            assert "name" not in item
        store.close()

    def test_full_mode_enriches(self, tmp_path):
        store = _make_store(tmp_path)
        from gathon.tools.query import query_graph
        result = query_graph(
            store, "a.py::bar", "callers_of",
            detail_level="full",
        )
        assert result["detail_level"] == "full"
        if result["count"] > 0:
            item = result["results"][0]
            assert "name" in item or "kind" in item
        store.close()


class TestGetNeighborsDisclosure:
    def test_index_mode(self, tmp_path):
        store = _make_store(tmp_path)
        from gathon.tools.query import get_neighbors
        result = get_neighbors(store, "a.py::foo")
        assert result["detail_level"] == "index"
        if result["count"] > 0:
            item = result["neighbors"][0]
            assert "qualified_name" in item
            assert "edge_kind" in item
            assert "file_type" not in item
        store.close()

    def test_full_mode(self, tmp_path):
        store = _make_store(tmp_path)
        from gathon.tools.query import get_neighbors
        result = get_neighbors(
            store, "a.py::foo", detail_level="full",
        )
        assert result["detail_level"] == "full"
        if result["count"] > 0:
            item = result["neighbors"][0]
            assert "file_type" in item or "kind" in item
        store.close()
