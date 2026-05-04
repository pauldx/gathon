"""Tests for cross-session memory engine."""

from __future__ import annotations

from gathon.memory.db import MemoryDB
from gathon.memory.roi import calculate_roi, gc_low_roi
from gathon.memory.search import find_contradictions, hybrid_search


class TestMemoryDB:
    def test_save_and_get(self, tmp_path):
        db = MemoryDB(db_path=tmp_path / "test.db")
        obs_id = db.save("note", "Test Title", "Test content here")
        assert obs_id > 0
        obs = db.get(obs_id)
        assert obs is not None
        assert obs.title == "Test Title"
        assert obs.content == "Test content here"
        assert obs.access_count >= 1
        db.close()

    def test_upsert_duplicate(self, tmp_path):
        db = MemoryDB(db_path=tmp_path / "test.db")
        id1 = db.save("note", "Same Title", "content v1")
        id2 = db.save("note", "Same Title", "content v2")
        assert id1 == id2
        obs = db.get(id1)
        assert "v2" in obs.content
        db.close()

    def test_search(self, tmp_path):
        db = MemoryDB(db_path=tmp_path / "test.db")
        db.save("note", "Python Tips", "Use list comprehensions for speed")
        db.save("note", "Rust Tips", "Use iterators and zero-cost abstractions")
        results = db.search("Python list")
        assert len(results) >= 1
        assert any("Python" in r.observation.title for r in results)
        db.close()

    def test_search_type_filter(self, tmp_path):
        db = MemoryDB(db_path=tmp_path / "test.db")
        db.save("note", "Note Thing", "some note")
        db.save("guardrail", "Guard Thing", "safety rule")
        results = db.search("Thing", type_filter="guardrail")
        assert all(r.observation.obs_type == "guardrail" for r in results)
        db.close()

    def test_index(self, tmp_path):
        db = MemoryDB(db_path=tmp_path / "test.db")
        db.save("note", "A", "content a")
        db.save("warning", "B", "content b")
        obs_list = db.index()
        assert len(obs_list) >= 2
        db.close()

    def test_delete(self, tmp_path):
        """delete() is a soft-delete (archived=1); archived obs are excluded from index."""
        db = MemoryDB(db_path=tmp_path / "test.db")
        obs_id = db.save("note", "To Delete", "bye")
        assert db.delete(obs_id)
        # index() excludes archived observations
        obs_list = db.index()
        assert all(o.id != obs_id for o in obs_list)
        db.close()

    def test_update(self, tmp_path):
        db = MemoryDB(db_path=tmp_path / "test.db")
        obs_id = db.save("note", "Updatable", "original")
        db.update(obs_id, content="modified", importance=0.9)
        obs = db.get(obs_id)
        assert "modified" in obs.content
        assert obs.importance == 0.9
        db.close()

    def test_decay(self, tmp_path):
        db = MemoryDB(db_path=tmp_path / "test.db")
        db.save("note", "Old Note", "old content")
        # Backdate and zero out access_count to trigger decay
        db._conn.execute(
            "UPDATE observations SET created_at = datetime('now', '-100 days'), "
            "last_accessed = datetime('now', '-100 days'), access_count = 0"
        )
        db._conn.commit()
        decayed = db.decay()
        assert decayed >= 1
        db.close()

    def test_immune_types_skip_decay(self, tmp_path):
        db = MemoryDB(db_path=tmp_path / "test.db")
        db.save("guardrail", "Never Delete", "important rule")
        db._conn.execute(
            "UPDATE observations SET created_at = datetime('now', '-9999 days'), "
            "last_accessed = datetime('now', '-9999 days'), access_count = 0"
        )
        db._conn.commit()
        decayed = db.decay()
        assert decayed == 0
        db.close()

    def test_promote(self, tmp_path):
        db = MemoryDB(db_path=tmp_path / "test.db")
        obs_id = db.save("note", "Frequent Note", "used a lot")
        db._conn.execute(
            "UPDATE observations SET access_count = 6 WHERE id = ?", (obs_id,)
        )
        db._conn.commit()
        promoted = db.promote()
        assert promoted >= 1
        obs = db.get(obs_id)
        assert obs.obs_type == "convention"
        db.close()

    def test_dedup(self, tmp_path):
        db = MemoryDB(db_path=tmp_path / "test.db")
        # Force-create duplicate via raw SQL (bypass upsert)
        db._conn.execute(
            "INSERT INTO observations (obs_type, title, content, importance, "
            "created_at, updated_at, last_accessed) "
            "VALUES (?, ?, ?, ?, datetime('now'), datetime('now'), datetime('now'))",
            ("note", "Dup", "content 1", 0.3),
        )
        db._conn.execute(
            "INSERT INTO observations (obs_type, title, content, importance, "
            "created_at, updated_at, last_accessed) "
            "VALUES (?, ?, ?, ?, datetime('now'), datetime('now'), datetime('now'))",
            ("note", "Dup", "content 2", 0.7),
        )
        db._conn.commit()
        deduped = db.dedup()
        assert deduped >= 1
        db.close()

    def test_maintain(self, tmp_path):
        db = MemoryDB(db_path=tmp_path / "test.db")
        db.save("note", "Maintain Me", "content")
        result = db.maintain()
        assert "decayed" in result
        assert "promoted" in result
        assert "deduped" in result
        db.close()

    def test_stats(self, tmp_path):
        db = MemoryDB(db_path=tmp_path / "test.db")
        db.save("note", "S1", "c1")
        db.save("guardrail", "S2", "c2")
        s = db.stats()
        assert s["total"] >= 2
        assert "note" in s["by_type"]
        db.close()

    def test_context_manager(self, tmp_path):
        with MemoryDB(db_path=tmp_path / "test.db") as db:
            db.save("note", "CM Test", "content")
            s = db.stats()
            assert s["total"] >= 1

    def test_get_many(self, tmp_path):
        db = MemoryDB(db_path=tmp_path / "test.db")
        id1 = db.save("note", "One", "c1")
        id2 = db.save("note", "Two", "c2")
        obs_list = db.get_many([id1, id2])
        assert len(obs_list) == 2
        db.close()


class TestROI:
    def test_calculate_roi(self):
        from gathon.memory.models import Observation
        obs = Observation(
            id=1, obs_type="note", title="T", content="C",
            importance=0.8, access_count=5,
            created_at="2026-04-29 00:00:00",
        )
        roi = calculate_roi(obs)
        assert roi > 0

    def test_gc_low_roi(self, tmp_path):
        db = MemoryDB(db_path=tmp_path / "test.db")
        db.save("note", "Low ROI", "forgotten", importance=0.01)
        db._conn.execute(
            "UPDATE observations SET access_count = 0, "
            "created_at = datetime('now', '-60 days'), "
            "last_accessed = datetime('now', '-60 days')"
        )
        db._conn.commit()
        archived = gc_low_roi(db, threshold=1.0)
        assert archived >= 1
        db.close()


class TestSearch:
    def test_hybrid_search(self, tmp_path):
        db = MemoryDB(db_path=tmp_path / "test.db")
        db.save("note", "Alpha Feature", "implements alpha protocol")
        db.save("note", "Beta Feature", "implements beta protocol")
        results = hybrid_search(db, "alpha protocol")
        assert len(results) >= 1
        db.close()

    def test_find_contradictions(self, tmp_path):
        db = MemoryDB(db_path=tmp_path / "test.db")
        id1 = db.save("convention", "Always use semicolons", "in JavaScript always use semicolons")
        db.save("convention", "Never use semicolons", "in JavaScript never use semicolons")
        contradictions = find_contradictions(db, id1)
        assert len(contradictions) >= 1
        db.close()
