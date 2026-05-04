"""Tests for content hash deduplication in UnifiedStore."""

from gathon.schema import UnifiedNode
from gathon.store import UnifiedStore, _compute_content_hash


class TestContentHash:
    def test_same_content_same_hash(self):
        n1 = UnifiedNode(
            kind="Function", name="foo",
            qualified_name="a.py::foo", file_path="a.py",
            file_type="code", label="Process data",
        )
        n2 = UnifiedNode(
            kind="Function", name="foo",
            qualified_name="a.py::foo", file_path="a.py",
            file_type="code", label="Process data",
        )
        assert _compute_content_hash(n1) == _compute_content_hash(n2)

    def test_different_content_different_hash(self):
        n1 = UnifiedNode(
            kind="Function", name="foo",
            qualified_name="a.py::foo", file_path="a.py",
            file_type="code", label="Process data",
        )
        n2 = UnifiedNode(
            kind="Function", name="foo",
            qualified_name="a.py::foo", file_path="a.py",
            file_type="code", label="Handle output",
        )
        assert _compute_content_hash(n1) != _compute_content_hash(n2)

    def test_hash_length(self):
        n = UnifiedNode(
            kind="Function", name="foo",
            qualified_name="a.py::foo", file_path="a.py",
        )
        assert len(_compute_content_hash(n)) == 16


class TestDedup:
    def test_skips_unchanged_node(self, tmp_path):
        db = tmp_path / "graph.db"
        store = UnifiedStore(str(db))
        node = UnifiedNode(
            kind="Function", name="foo",
            qualified_name="a.py::foo", file_path="a.py",
            language="python", pipeline="code_graph",
        )
        id1 = store.upsert_unified_node(node)
        store.commit()

        # Same node again — should skip write, return same ID
        id2 = store.upsert_unified_node(node)
        assert id2 == id1

        # Verify only 1 row
        count = store._conn.execute(
            "SELECT COUNT(*) FROM nodes WHERE qualified_name = ?",
            ("a.py::foo",),
        ).fetchone()[0]
        assert count == 1
        store.close()

    def test_updates_changed_node(self, tmp_path):
        db = tmp_path / "graph.db"
        store = UnifiedStore(str(db))
        node = UnifiedNode(
            kind="Function", name="foo",
            qualified_name="a.py::foo", file_path="a.py",
            language="python", pipeline="code_graph",
            label="Original label",
        )
        store.upsert_unified_node(node)
        store.commit()

        # Change label — content hash differs, should update
        node2 = UnifiedNode(
            kind="Function", name="foo",
            qualified_name="a.py::foo", file_path="a.py",
            language="python", pipeline="code_graph",
            label="Updated label",
        )
        store.upsert_unified_node(node2)
        store.commit()

        row = store._conn.execute(
            "SELECT label, content_hash FROM nodes WHERE qualified_name = ?",
            ("a.py::foo",),
        ).fetchone()
        assert row[0] == "Updated label"
        assert row[1] == _compute_content_hash(node2)
        store.close()

    def test_content_hash_column_exists(self, tmp_path):
        db = tmp_path / "graph.db"
        store = UnifiedStore(str(db))
        cols = [
            row[1] for row in
            store._conn.execute("PRAGMA table_info(nodes)").fetchall()
        ]
        assert "content_hash" in cols
        store.close()

    def test_different_qualified_names_not_deduped(self, tmp_path):
        db = tmp_path / "graph.db"
        store = UnifiedStore(str(db))
        n1 = UnifiedNode(
            kind="Function", name="foo",
            qualified_name="a.py::foo", file_path="a.py",
        )
        n2 = UnifiedNode(
            kind="Function", name="foo",
            qualified_name="b.py::foo", file_path="b.py",
        )
        store.upsert_unified_node(n1)
        store.upsert_unified_node(n2)
        store.commit()

        count = store._conn.execute(
            "SELECT COUNT(*) FROM nodes",
        ).fetchone()[0]
        assert count == 2
        store.close()
