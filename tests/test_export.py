"""Tests for gathon.export — graph export formats."""

import json

from gathon.export import _FILE_TYPE_COLORS, export_unified
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


def test_export_json(tmp_path):
    store = _make_store(tmp_path)
    out = str(tmp_path / "out.json")
    result = export_unified(store, out, "json")

    assert result["format"] == "json"
    assert result["nodes"] == 2
    assert result["edges"] == 1

    data = json.loads((tmp_path / "out.json").read_text())
    assert len(data["nodes"]) == 2
    assert len(data["edges"]) == 1
    assert data["meta"]["node_count"] == 2

    colors = {n["color"] for n in data["nodes"]}
    assert _FILE_TYPE_COLORS["code"] in colors
    assert _FILE_TYPE_COLORS["document"] in colors
    store.close()


def test_export_graphml(tmp_path):
    store = _make_store(tmp_path)
    out = str(tmp_path / "out.graphml")
    result = export_unified(store, out, "graphml")

    assert result["format"] == "graphml"
    assert result["nodes"] == 2
    assert (tmp_path / "out.graphml").exists()
    store.close()


def test_export_unsupported(tmp_path):
    store = _make_store(tmp_path)
    result = export_unified(store, "/dev/null", "pdf")
    assert "error" in result
    store.close()


def test_export_json_node_fields(tmp_path):
    store = _make_store(tmp_path)
    out = str(tmp_path / "out.json")
    export_unified(store, out, "json")

    data = json.loads((tmp_path / "out.json").read_text())
    node = next(n for n in data["nodes"] if n["label"] == "foo")
    assert node["kind"] == "Function"
    assert node["file_path"] == "a.py"
    assert node["file_type"] == "code"
    store.close()


def test_export_json_edge_fields(tmp_path):
    store = _make_store(tmp_path)
    out = str(tmp_path / "out.json")
    export_unified(store, out, "json")

    data = json.loads((tmp_path / "out.json").read_text())
    edge = data["edges"][0]
    assert edge["kind"] == "REFERENCES"
    assert edge["source"] == "doc.md::intro"
    assert edge["target"] == "a.py::foo"
    assert "color" in edge
    store.close()
