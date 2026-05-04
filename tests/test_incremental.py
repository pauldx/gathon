"""Tests for gathon.incremental — hash + git diff updates."""


from gathon.incremental import (
    collect_files,
    full_build,
    get_file_hash,
    incremental_update,
)
from gathon.store import UnifiedStore


def test_collect_files(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n")
    (tmp_path / "b.md").write_text("# Hi\n")
    (tmp_path / ".hidden").write_text("secret\n")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "c.js").write_text("//\n")
    (tmp_path / "d.pyc").write_bytes(b"\x00")

    files = collect_files(tmp_path)
    names = {f.name for f in files}
    assert "a.py" in names
    assert "b.md" in names
    assert ".hidden" not in names
    assert "c.js" not in names
    assert "d.pyc" not in names


def test_get_file_hash(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("hello")
    h1 = get_file_hash(f)
    assert len(h1) == 64

    f.write_text("hello")
    h2 = get_file_hash(f)
    assert h1 == h2

    f.write_text("world")
    h3 = get_file_hash(f)
    assert h3 != h1


def test_full_build(tmp_path):
    (tmp_path / "main.py").write_text("def f(): pass\n")
    (tmp_path / "conf.yaml").write_text("key: val\n")

    db = tmp_path / "graph.db"
    store = UnifiedStore(str(db))
    result = full_build(tmp_path, store)

    assert result["total_files"] >= 2
    stats = store.get_unified_stats()
    assert stats["total_nodes"] > 0
    store.close()


def test_full_build_removes_stale(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n")
    db = tmp_path / "graph.db"
    store = UnifiedStore(str(db))

    full_build(tmp_path, store)
    assert store.get_unified_stats()["total_nodes"] > 0

    (tmp_path / "a.py").unlink()
    result = full_build(tmp_path, store)
    assert result["stale_removed"] >= 1
    store.close()


def test_incremental_explicit_files(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n")
    db = tmp_path / "graph.db"
    store = UnifiedStore(str(db))

    full_build(tmp_path, store)

    (tmp_path / "a.py").write_text("x = 2\n")
    result = incremental_update(
        tmp_path, store,
        changed_files=["a.py"],
    )
    assert result["changed_files"] == ["a.py"]
    store.close()


def test_incremental_no_changes(tmp_path):
    db = tmp_path / "graph.db"
    store = UnifiedStore(str(db))
    result = incremental_update(
        tmp_path, store, changed_files=[],
    )
    assert result["files_updated"] == 0
    store.close()


def test_incremental_deleted_file(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n")
    db = tmp_path / "graph.db"
    store = UnifiedStore(str(db))
    full_build(tmp_path, store)

    (tmp_path / "a.py").unlink()
    result = incremental_update(
        tmp_path, store, changed_files=["a.py"],
    )
    assert result["removed"] >= 1
    store.close()
