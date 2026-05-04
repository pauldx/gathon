"""Tests for compression telemetry logging and stats."""

import sqlite3

from gathon.store import UnifiedStore
from gathon.telemetry import TelemetryLogger, TelemetryStats


def _make_conn(tmp_path) -> sqlite3.Connection:
    """Create a store (runs migrations) and return its connection."""
    db = tmp_path / "graph.db"
    store = UnifiedStore(str(db))
    conn = store._conn
    return conn, store


class TestTelemetryLogger:
    def test_log_compression(self, tmp_path):
        conn, store = _make_conn(tmp_path)
        tl = TelemetryLogger(conn)
        tl.log_compression(
            "semantic_search",
            {"results": [{"a": 1}] * 10},
            {"results": [{"a": 1}] * 5},
            "full",
        )
        row = conn.execute(
            "SELECT tool_name, event_type, intensity FROM compression_telemetry"
        ).fetchone()
        assert row[0] == "semantic_search"
        assert row[1] == "compress"
        assert row[2] == "full"
        store.close()

    def test_log_compression_savings(self, tmp_path):
        conn, store = _make_conn(tmp_path)
        tl = TelemetryLogger(conn)
        before = {"data": "x" * 400}
        after = {"data": "x" * 100}
        tl.log_compression("get_node", before, after, "lite")
        row = conn.execute(
            "SELECT before_tokens, after_tokens, savings_tokens, savings_pct "
            "FROM compression_telemetry"
        ).fetchone()
        assert row[0] > row[1]
        assert row[2] == row[0] - row[1]
        assert row[3] > 0
        store.close()

    def test_log_disclosure(self, tmp_path):
        conn, store = _make_conn(tmp_path)
        tl = TelemetryLogger(conn)
        tl.log_disclosure("query_graph", "index", 50)
        row = conn.execute(
            "SELECT tool_name, event_type, detail_level, after_tokens "
            "FROM compression_telemetry"
        ).fetchone()
        assert row[0] == "query_graph"
        assert row[1] == "disclosure"
        assert row[2] == "index"
        assert row[3] == 50
        store.close()

    def test_multiple_events(self, tmp_path):
        conn, store = _make_conn(tmp_path)
        tl = TelemetryLogger(conn)
        tl.log_compression("t1", {"a": "b"}, {"a": "b"}, "lite")
        tl.log_compression("t2", {"a": "b"}, {"a": "b"}, "full")
        tl.log_disclosure("t3", "full", 100)
        count = conn.execute(
            "SELECT COUNT(*) FROM compression_telemetry"
        ).fetchone()[0]
        assert count == 3
        store.close()


class TestTelemetryStats:
    def _seed(self, conn):
        tl = TelemetryLogger(conn)
        tl.log_compression("search", {"d": "x" * 200}, {"d": "x" * 80}, "full")
        tl.log_compression("search", {"d": "x" * 100}, {"d": "x" * 40}, "full")
        tl.log_compression("get_node", {"d": "x" * 50}, {"d": "x" * 30}, "lite")
        tl.log_disclosure("search", "index", 25)
        tl.log_disclosure("search", "full", 120)
        tl.log_disclosure("search", "index", 30)

    def test_compression_summary(self, tmp_path):
        conn, store = _make_conn(tmp_path)
        self._seed(conn)
        ts = TelemetryStats(conn)
        s = ts.get_compression_summary()
        assert s["total_events"] == 3
        assert s["total_savings_tokens"] > 0
        assert s["total_before_tokens"] > s["total_after_tokens"]
        store.close()

    def test_per_tool_breakdown(self, tmp_path):
        conn, store = _make_conn(tmp_path)
        self._seed(conn)
        ts = TelemetryStats(conn)
        tools = ts.get_per_tool_breakdown()
        names = [t["tool"] for t in tools]
        assert "search" in names
        assert "get_node" in names
        search = next(t for t in tools if t["tool"] == "search")
        assert search["events"] == 2
        store.close()

    def test_per_intensity_breakdown(self, tmp_path):
        conn, store = _make_conn(tmp_path)
        self._seed(conn)
        ts = TelemetryStats(conn)
        intensities = ts.get_per_intensity_breakdown()
        labels = [i["intensity"] for i in intensities]
        assert "full" in labels
        assert "lite" in labels
        store.close()

    def test_disclosure_stats(self, tmp_path):
        conn, store = _make_conn(tmp_path)
        self._seed(conn)
        ts = TelemetryStats(conn)
        d = ts.get_disclosure_stats()
        assert d["total_queries"] == 3
        assert d["index_queries"] == 2
        assert d["full_queries"] == 1
        assert 0 < d["upgrade_rate_pct"] < 100
        store.close()

    def test_trend(self, tmp_path):
        conn, store = _make_conn(tmp_path)
        self._seed(conn)
        ts = TelemetryStats(conn)
        trend = ts.get_trend(days=7)
        assert len(trend) >= 1
        assert trend[0]["events"] > 0
        store.close()

    def test_full_stats(self, tmp_path):
        conn, store = _make_conn(tmp_path)
        self._seed(conn)
        ts = TelemetryStats(conn)
        full = ts.get_full_stats(7)
        assert "summary" in full
        assert "by_tool" in full
        assert "by_intensity" in full
        assert "disclosure" in full
        assert "trend" in full
        store.close()

    def test_empty_stats(self, tmp_path):
        conn, store = _make_conn(tmp_path)
        ts = TelemetryStats(conn)
        s = ts.get_compression_summary()
        assert s["total_events"] == 0
        assert s["total_savings_tokens"] == 0
        d = ts.get_disclosure_stats()
        assert d["total_queries"] == 0
        store.close()
