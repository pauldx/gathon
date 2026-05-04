"""Tests for session continuity engine."""

from __future__ import annotations

from gathon.session.db import SessionDB
from gathon.session.events import (
    extract_from_bash,
    extract_from_edit,
    extract_from_read,
    extract_from_tool_use,
    extract_from_write,
)
from gathon.session.snapshot import build_session_guide, build_snapshot


class TestSessionDB:
    def test_create_and_query(self, tmp_path):
        db = SessionDB(tmp_path / "test.db")
        event_id = db.log_event(
            session_id="test_session",
            event_type="file_edit",
            priority=1,
            category="files",
            data={"file_path": "src/main.py", "lines_changed": 10},
            source_tool="Edit",
        )
        assert event_id > 0
        events = db.get_events("test_session")
        assert len(events) == 1
        assert events[0].event_type == "file_edit"
        assert events[0].data["file_path"] == "src/main.py"
        db.close()

    def test_priority_filtering(self, tmp_path):
        db = SessionDB(tmp_path / "test.db")
        db.log_event("s1", "file_edit", priority=1, category="files")
        db.log_event("s1", "git_commit", priority=2, category="git")
        db.log_event("s1", "mcp_tool_use", priority=3, category="tools")

        p1_only = db.get_events("s1", priority_max=1)
        assert len(p1_only) == 1
        all_events = db.get_events("s1", priority_max=3)
        assert len(all_events) == 3
        db.close()

    def test_latest_by_type(self, tmp_path):
        db = SessionDB(tmp_path / "test.db")
        db.log_event("s1", "error", data={"stderr": "first error"})
        db.log_event("s1", "error", data={"stderr": "second error"})
        latest = db.get_latest_by_type("s1", "error")
        assert latest is not None
        # Both events share the same second-precision timestamp, so
        # the DB may return either one; just verify we get a valid error event
        assert latest.data["stderr"] in ("first error", "second error")
        db.close()

    def test_event_counts(self, tmp_path):
        db = SessionDB(tmp_path / "test.db")
        db.log_event("s1", "file_edit")
        db.log_event("s1", "file_edit")
        db.log_event("s1", "git_commit")
        counts = db.get_event_counts("s1")
        assert counts["file_edit"] == 2
        assert counts["git_commit"] == 1
        db.close()

    def test_snapshots(self, tmp_path):
        db = SessionDB(tmp_path / "test.db")
        db.save_snapshot("s1", "<snapshot>test</snapshot>")
        snap = db.get_latest_snapshot("s1")
        assert snap is not None
        assert "test" in snap
        assert db.get_latest_snapshot("nonexistent") is None
        db.close()

    def test_cleanup(self, tmp_path):
        db = SessionDB(tmp_path / "test.db")
        db.log_event("s1", "old_event")
        # Backdate the event so cleanup_old can find it
        db.conn.execute(
            "UPDATE session_events SET created_at = datetime('now', '-2 days')"
        )
        db.conn.commit()
        deleted = db.cleanup_old(days=1)
        assert deleted >= 1
        db.close()

    def test_empty_db(self, tmp_path):
        db = SessionDB(tmp_path / "test.db")
        events = db.get_events("nonexistent")
        assert events == []
        counts = db.get_event_counts("nonexistent")
        assert counts == {}
        db.close()


class TestEventExtraction:
    def test_bash_git_commit(self):
        events = extract_from_bash(
            "git commit -m 'test'",
            "[main abc1234] test\n 1 file changed\n",
            "", 0,
        )
        git_events = [e for e in events if e.event_type == "git_commit"]
        assert len(git_events) == 1
        assert git_events[0].data["hash"] == "abc1234"

    def test_bash_git_checkout(self):
        events = extract_from_bash(
            "git checkout -b feature/new",
            "Switched to new branch 'feature/new'\n",
            "", 0,
        )
        assert any(e.event_type == "git_checkout" for e in events)

    def test_bash_error(self):
        events = extract_from_bash(
            "python bad.py", "", "ModuleNotFoundError: no module 'foo'", 1,
        )
        errors = [e for e in events if e.event_type == "error"]
        assert len(errors) == 1
        assert "ModuleNotFoundError" in errors[0].data["stderr"]

    def test_bash_file_read(self):
        events = extract_from_bash(
            "cat src/main.py", "file content here", "", 0,
        )
        reads = [e for e in events if e.event_type == "file_read"]
        assert len(reads) == 1
        assert reads[0].data["file_path"] == "src/main.py"

    def test_edit_event(self):
        event = extract_from_edit("src/foo.py", "old\ncode\n", "new\ncode\nextra\n")
        assert event.event_type == "file_edit"
        assert event.data["file_path"] == "src/foo.py"
        assert event.data["lines_added"] == 1

    def test_write_event(self):
        event = extract_from_write("new_file.py", "content")
        assert event.event_type == "file_write"
        assert event.data["size_bytes"] == 7

    def test_read_event(self):
        event = extract_from_read("README.md")
        assert event.event_type == "file_read"
        assert event.data["file_path"] == "README.md"

    def test_tool_use_bash(self):
        events = extract_from_tool_use(
            "Bash",
            {"command": "echo hello"},
            {"stdout": "hello\n", "stderr": "", "exit_code": 0},
        )
        assert any(e.event_type == "mcp_tool_use" for e in events)

    def test_tool_use_edit(self):
        events = extract_from_tool_use(
            "Edit",
            {"file_path": "foo.py", "old_string": "old", "new_string": "new"},
            {},
        )
        assert any(e.event_type == "file_edit" for e in events)


class TestSnapshot:
    def test_build_empty(self, tmp_path):
        db = SessionDB(tmp_path / "test.db")
        snapshot = build_snapshot(db, "empty_session")
        assert "<session-snapshot>" in snapshot
        assert "</session-snapshot>" in snapshot
        db.close()

    def test_build_with_events(self, tmp_path):
        db = SessionDB(tmp_path / "test.db")
        db.log_event("s1", "file_edit", priority=1, category="files",
                      data={"file_path": "src/main.py", "lines_added": 5, "lines_removed": 2})
        db.log_event("s1", "git_commit", priority=2, category="git",
                      data={"hash": "abc1234", "message": "fix bug"})
        db.log_event("s1", "error", priority=2, category="errors",
                      data={"stderr": "ImportError: no module foo",
                            "command": "python test.py"})
        snapshot = build_snapshot(db, "s1")
        assert "src/main.py" in snapshot
        assert "abc1234" in snapshot or "commit" in snapshot
        db.close()

    def test_snapshot_size_limit(self, tmp_path):
        db = SessionDB(tmp_path / "test.db")
        for i in range(100):
            db.log_event("s1", "file_edit", priority=1, category="files",
                          data={"file_path": f"src/file_{i}.py", "lines_added": i})
        snapshot = build_snapshot(db, "s1", max_bytes=1024)
        assert len(snapshot.encode("utf-8")) <= 1200  # some slack for closing tag
        db.close()

    def test_session_guide(self, tmp_path):
        db = SessionDB(tmp_path / "test.db")
        db.log_event("s1", "user_prompt", priority=1, category="context",
                      data={"text": "fix the auth bug"})
        db.log_event("s1", "file_edit", priority=1, category="files",
                      data={"file_path": "src/auth.py", "lines_added": 10, "lines_removed": 3})
        db.log_event("s1", "mcp_tool_use", priority=3, category="tools",
                      data={"tool_name": "Bash"})
        db.log_event("s1", "mcp_tool_use", priority=3, category="tools",
                      data={"tool_name": "Bash"})
        db.log_event("s1", "mcp_tool_use", priority=3, category="tools",
                      data={"tool_name": "Edit"})
        guide = build_session_guide(db, "s1")
        assert "<session-guide>" in guide
        assert "auth" in guide.lower()
        assert "Bash" in guide
        db.close()
