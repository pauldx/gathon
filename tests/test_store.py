"""Tests for gathon.store — UnifiedStore with migrations and unified ops."""


import pytest

from gathon.schema import UnifiedEdge, UnifiedNode
from gathon.store import GATHON_LATEST, UnifiedStore


@pytest.fixture
def store(tmp_path):
    db = tmp_path / "test.db"
    s = UnifiedStore(str(db))
    yield s
    s.close()


def test_migrations_applied(store):
    version = store._conn.execute(
        "SELECT value FROM metadata WHERE key='schema_version'"
    ).fetchone()
    assert version is not None
    assert int(version[0]) >= GATHON_LATEST


def test_new_columns_exist(store):
    cols = {row[1] for row in store._conn.execute("PRAGMA table_info(nodes)")}
    for col in ["label", "file_type", "source_url", "confidence", "pipeline", "author"]:
        assert col in cols, f"Missing column: {col}"

    edge_cols = {row[1] for row in store._conn.execute("PRAGMA table_info(edges)")}
    assert "relation" in edge_cols
    assert "weight" in edge_cols


def test_new_tables_exist(store):
    tables = {row[0] for row in store._conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    assert "hyperedges" in tables
    assert "pipeline_runs" in tables


def test_upsert_unified_node(store):
    node = UnifiedNode(
        kind="Function", name="hello", qualified_name="test.py::hello",
        file_path="test.py", line_start=1, line_end=5, language="python",
        pipeline="code_graph",
    )
    nid = store.upsert_unified_node(node)
    assert nid > 0

    nid2 = store.upsert_unified_node(node)
    assert nid2 == nid


def test_upsert_unified_edge(store):
    edge = UnifiedEdge(
        kind="CALLS", source_qualified="a::f", target_qualified="a::g",
        file_path="a.py", line=10,
    )
    eid = store.upsert_unified_edge(edge)
    assert eid > 0

    eid2 = store.upsert_unified_edge(edge)
    assert eid2 == eid


def test_store_unified_file(store):
    nodes = [
        UnifiedNode(kind="File", name="a.py", qualified_name="a.py", file_path="a.py"),
        UnifiedNode(kind="Function", name="f", qualified_name="a.py::f", file_path="a.py"),
    ]
    edges = [
        UnifiedEdge(
            kind="CONTAINS", source_qualified="a.py",
            target_qualified="a.py::f", file_path="a.py",
        ),
    ]
    store.store_unified_file("a.py", nodes, edges, file_hash="abc123", pipeline="code_graph")
    store.commit()

    stats = store.get_unified_stats()
    assert stats["total_nodes"] == 2
    assert stats["total_edges"] == 1

    run = store.get_pipeline_run("a.py")
    assert run is not None
    assert run["pipeline"] == "code_graph"
    assert run["file_hash"] == "abc123"


def test_store_extraction_dict(store):
    data = {
        "nodes": [
            {"id": "intro", "label": "Intro", "file_type": "document", "source_file": "r.md"},
            {"id": "setup", "label": "Setup", "file_type": "document", "source_file": "r.md"},
        ],
        "edges": [
            {"source": "intro", "target": "setup", "relation": "contains", "source_file": "r.md"},
        ],
    }
    store.store_extraction_dict(data)
    store.commit()

    stats = store.get_unified_stats()
    assert stats["total_nodes"] == 2
    assert stats["nodes_by_file_type"].get("document", 0) == 2


def test_build_networkx_graph(store):
    n1 = UnifiedNode(kind="Function", name="f", qualified_name="a::f", file_path="a.py")
    n2 = UnifiedNode(kind="Function", name="g", qualified_name="a::g", file_path="a.py")
    store.upsert_unified_node(n1)
    store.upsert_unified_node(n2)
    store.upsert_unified_edge(
        UnifiedEdge(
            kind="CALLS", source_qualified="a::f",
            target_qualified="a::g", file_path="a.py",
        )
    )
    store.commit()

    g = store.build_networkx_graph()
    assert g.number_of_nodes() == 2
    assert g.number_of_edges() == 1
    assert g.has_edge("a::f", "a::g")


def test_networkx_cache(store):
    n1 = UnifiedNode(kind="Function", name="f", qualified_name="a::f", file_path="a.py")
    store.upsert_unified_node(n1)
    store.commit()

    g1 = store.build_networkx_graph()
    g2 = store.build_networkx_graph()
    assert g1 is g2

    store.upsert_unified_node(
        UnifiedNode(kind="Function", name="g", qualified_name="a::g", file_path="a.py")
    )
    g3 = store.build_networkx_graph()
    assert g3 is not g1


def test_code_graph_compatibility(store):
    """Base methods still work on extended schema."""
    from gathon.code_graph.parser import NodeInfo

    node = NodeInfo(
        kind="Function", name="hello", file_path="test.py",
        line_start=1, line_end=5, language="python",
    )
    nid = store.upsert_node(node, "abc")
    assert nid > 0

    retrieved = store.get_node("test.py::hello")
    assert retrieved is not None
    assert retrieved.name == "hello"
