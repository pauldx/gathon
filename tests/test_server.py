"""Tests for gathon.server — MCP tool registration and basic tool calls."""

from gathon.schema import UnifiedEdge, UnifiedNode
from gathon.server import mcp
from gathon.store import UnifiedStore


def test_tool_count():
    tools = mcp._tool_manager._tools
    assert len(tools) >= 28


def test_required_tools_registered():
    tools = set(mcp._tool_manager._tools.keys())
    required = {
        "build_graph", "query_graph", "semantic_search",
        "get_node", "get_neighbors", "shortest_path",
        "get_minimal_context", "get_impact_radius",
        "get_review_context", "detect_changes",
        "list_flows", "get_flow",
        "list_communities", "get_community",
        "get_architecture_overview",
        "list_graph_stats", "god_nodes",
        "get_bridge_nodes", "get_knowledge_gaps",
        "get_surprising_connections",
        "refactor", "find_large_functions",
        "export_graph", "generate_wiki",
        "traverse_graph", "cross_repo_search",
    }
    missing = required - tools
    assert not missing, f"Missing tools: {missing}"


def _make_store_with_data(tmp_path):
    db = tmp_path / "graph.db"
    store = UnifiedStore(str(db))
    nodes = [
        UnifiedNode(
            kind="Function", name="foo",
            qualified_name="a.py::foo", file_path="a.py",
            line_start=1, line_end=10, language="python",
            pipeline="code_graph",
        ),
        UnifiedNode(
            kind="Function", name="bar",
            qualified_name="a.py::bar", file_path="a.py",
            line_start=12, line_end=20, language="python",
            pipeline="code_graph",
        ),
        UnifiedNode(
            kind="Section", name="intro",
            qualified_name="doc.md::intro", file_path="doc.md",
            file_type="document", pipeline="gathon_doc",
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
            relation="references",
        ),
    ]
    for n in nodes:
        store.upsert_unified_node(n)
    for e in edges:
        store.upsert_unified_edge(e)
    store.commit()
    return store


class TestQueryTools:
    def test_query_callers(self, tmp_path):
        store = _make_store_with_data(tmp_path)
        from gathon.tools.query import query_graph
        result = query_graph(store, "a.py::bar", "callers_of")
        assert result["count"] >= 1
        store.close()

    def test_query_callees(self, tmp_path):
        store = _make_store_with_data(tmp_path)
        from gathon.tools.query import query_graph
        result = query_graph(store, "a.py::foo", "callees_of")
        assert result["count"] >= 1
        store.close()

    def test_query_bfs(self, tmp_path):
        store = _make_store_with_data(tmp_path)
        from gathon.tools.query import query_graph
        result = query_graph(
            store, "a.py::foo", mode="bfs", max_depth=2,
        )
        assert result["count"] >= 1
        store.close()

    def test_semantic_search(self, tmp_path):
        store = _make_store_with_data(tmp_path)
        from gathon.tools.query import semantic_search
        result = semantic_search(store, "foo")
        assert result["count"] >= 0
        store.close()

    def test_get_node_detail(self, tmp_path):
        store = _make_store_with_data(tmp_path)
        from gathon.tools.query import get_node_detail
        result = get_node_detail(store, "a.py::foo")
        assert result["name"] == "foo"
        assert result["kind"] == "Function"
        store.close()

    def test_get_neighbors(self, tmp_path):
        store = _make_store_with_data(tmp_path)
        from gathon.tools.query import get_neighbors
        result = get_neighbors(store, "a.py::foo")
        assert result["count"] >= 1
        store.close()

    def test_shortest_path(self, tmp_path):
        store = _make_store_with_data(tmp_path)
        from gathon.tools.query import shortest_path
        result = shortest_path(store, "a.py::foo", "a.py::bar")
        assert result["connected"]
        assert result["length"] == 1
        store.close()

    def test_shortest_path_cross_domain(self, tmp_path):
        store = _make_store_with_data(tmp_path)
        from gathon.tools.query import shortest_path
        result = shortest_path(
            store, "doc.md::intro", "a.py::bar",
        )
        assert result["connected"]
        assert result["length"] == 2
        store.close()


class TestAnalysisTools:
    def test_stats(self, tmp_path):
        store = _make_store_with_data(tmp_path)
        from gathon.tools.analysis import list_graph_stats
        result = list_graph_stats(store)
        assert result["total_nodes"] == 3
        assert result["total_edges"] == 2
        store.close()

    def test_god_nodes(self, tmp_path):
        store = _make_store_with_data(tmp_path)
        from gathon.tools.analysis import god_nodes
        result = god_nodes(store, top_n=5)
        assert result["count"] >= 1
        store.close()

    def test_god_nodes_code_scope(self, tmp_path):
        store = _make_store_with_data(tmp_path)
        from gathon.tools.analysis import god_nodes
        result = god_nodes(store, top_n=5, scope="code")
        for n in result["nodes"]:
            assert n["kind"] != "Section"
        store.close()

    def test_surprising_connections(self, tmp_path):
        store = _make_store_with_data(tmp_path)
        from gathon.tools.analysis import (
            get_surprising_connections,
        )
        result = get_surprising_connections(store)
        assert result["count"] >= 1
        store.close()

    def test_knowledge_gaps(self, tmp_path):
        store = _make_store_with_data(tmp_path)
        from gathon.tools.analysis import get_knowledge_gaps
        result = get_knowledge_gaps(store)
        assert "isolated_nodes" in result
        store.close()


class TestContextTools:
    def test_minimal_context(self, tmp_path):
        store = _make_store_with_data(tmp_path)
        from gathon.tools.context import get_minimal_context
        result = get_minimal_context(store, "review code")
        assert result["total_nodes"] == 3
        assert "next_tool_suggestions" in result
        store.close()

    def test_review_context(self, tmp_path):
        store = _make_store_with_data(tmp_path)
        from gathon.tools.context import (
            get_review_context as _grc,
        )
        result = _grc(store, "a.py")
        assert result["count"] >= 0
        store.close()
