"""Tests for CTP hook JSON protocol."""

from __future__ import annotations

import json

from gathon.cli_token_parse.engine import has_filter, load_filters


class TestHookMatching:
    def setup_method(self):
        load_filters()

    def test_matches_git_status(self):
        assert has_filter("git status")

    def test_no_match_echo(self):
        assert not has_filter("echo hello")

    def test_no_double_rewrite(self):
        assert not has_filter("gathon ctp git status")

    def test_compound_first_segment(self):
        assert has_filter("git status && echo done")


class TestHookProtocol:
    def test_expected_input_format(self):
        payload = {
            "tool_name": "Bash",
            "tool_input": {"command": "git status"},
        }
        raw = json.dumps(payload)
        data = json.loads(raw)
        assert data["tool_name"] == "Bash"
        assert data["tool_input"]["command"] == "git status"

    def test_expected_output_format(self):
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow",
                "permissionDecisionReason": "gathon ctp auto-rewrite",
                "updatedInput": {"command": "gathon ctp git status"},
            }
        }
        raw = json.dumps(output)
        data = json.loads(raw)
        assert data["hookSpecificOutput"]["updatedInput"]["command"].startswith("gathon ctp")


class TestTelemetry:
    def test_telemetry_db(self, tmp_path):
        from gathon.cli_token_parse.telemetry import CtpTelemetryDB

        db = CtpTelemetryDB(tmp_path / "test.db")
        db.log_filter("git_status", "git status", 200, 40, 5.0)
        db.log_filter("git_log", "git log -10", 500, 100, 8.0)

        s = db.get_summary()
        assert s["total_commands"] == 2
        assert s["total_savings"] == 560

        by_filter = db.get_by_filter()
        names = [f["filter"] for f in by_filter]
        assert "git_status" in names
        assert "git_log" in names

        history = db.get_history()
        assert len(history) == 2
        assert history[0]["filter"] == "git_log"

        db.close()

    def test_empty_telemetry(self, tmp_path):
        from gathon.cli_token_parse.telemetry import CtpTelemetryDB

        db = CtpTelemetryDB(tmp_path / "empty.db")
        s = db.get_summary()
        assert s["total_commands"] == 0
        assert s["total_savings"] == 0
        db.close()
