"""Tests for stored text compression in UnifiedStore."""

from gathon.schema import UnifiedNode
from gathon.store import UnifiedStore


def test_compressed_label_column_exists(tmp_path):
    db = tmp_path / "graph.db"
    store = UnifiedStore(str(db))
    cols = [
        row[1] for row in
        store._conn.execute("PRAGMA table_info(nodes)").fetchall()
    ]
    assert "compressed_label" in cols
    store.close()


def test_no_compression_when_off(tmp_path):
    db = tmp_path / "graph.db"
    store = UnifiedStore(str(db), compress_intensity="off")
    node = UnifiedNode(
        kind="Section", name="intro",
        qualified_name="doc.md::intro", file_path="doc.md",
        file_type="document", pipeline="gathon_doc",
        label="This is basically a really long introduction to the topic.",
    )
    store.upsert_unified_node(node)
    store.commit()

    row = store._conn.execute(
        "SELECT compressed_label FROM nodes WHERE qualified_name = ?",
        ("doc.md::intro",),
    ).fetchone()
    assert row[0] == ""
    store.close()


def test_compression_on_document_nodes(tmp_path):
    db = tmp_path / "graph.db"
    store = UnifiedStore(str(db), compress_intensity="full")
    node = UnifiedNode(
        kind="Section", name="intro",
        qualified_name="doc.md::intro", file_path="doc.md",
        file_type="document", pipeline="gathon_doc",
        label="This is basically a really simple introduction to the topic of database management.",
    )
    store.upsert_unified_node(node)
    store.commit()

    row = store._conn.execute(
        "SELECT label, compressed_label FROM nodes WHERE qualified_name = ?",
        ("doc.md::intro",),
    ).fetchone()
    original_label, compressed = row
    assert original_label == node.label
    assert compressed != ""
    assert "basically" not in compressed
    assert len(compressed) < len(original_label)
    store.close()


def test_no_compression_on_code_nodes(tmp_path):
    db = tmp_path / "graph.db"
    store = UnifiedStore(str(db), compress_intensity="full")
    node = UnifiedNode(
        kind="Function", name="foo",
        qualified_name="main.py::foo", file_path="main.py",
        file_type="code", pipeline="code_graph",
        label="This is basically a function.",
    )
    store.upsert_unified_node(node)
    store.commit()

    row = store._conn.execute(
        "SELECT compressed_label FROM nodes WHERE qualified_name = ?",
        ("main.py::foo",),
    ).fetchone()
    assert row[0] == ""
    store.close()


def test_ultra_compression_abbreviates(tmp_path):
    db = tmp_path / "graph.db"
    store = UnifiedStore(str(db), compress_intensity="ultra")
    node = UnifiedNode(
        kind="Section", name="config",
        qualified_name="doc.md::config", file_path="doc.md",
        file_type="document", pipeline="gathon_doc",
        label="The database authentication configuration management section.",
    )
    store.upsert_unified_node(node)
    store.commit()

    row = store._conn.execute(
        "SELECT compressed_label FROM nodes WHERE qualified_name = ?",
        ("doc.md::config",),
    ).fetchone()
    compressed = row[0]
    assert "DB" in compressed
    assert "auth" in compressed
    assert "config" in compressed
    store.close()
