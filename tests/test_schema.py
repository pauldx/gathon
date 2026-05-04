"""Tests for gathon.schema — UnifiedNode/UnifiedEdge dataclasses."""

from gathon.schema import (
    CONFIDENCE_SCORES,
    Confidence,
    EdgeKind,
    FileType,
    NodeKind,
    Pipeline,
    UnifiedEdge,
    UnifiedNode,
)


def test_unified_node_defaults():
    node = UnifiedNode(kind="Function", name="foo", qualified_name="a.py::foo", file_path="a.py")
    assert node.label == "foo"
    assert node.file_type == FileType.CODE
    assert node.confidence == Confidence.EXTRACTED
    assert node.confidence_score == 1.0
    assert node.pipeline == ""
    assert node.extra == {}


def test_unified_node_label_override():
    node = UnifiedNode(
        kind="Section", name="intro", qualified_name="doc::intro",
        file_path="doc.md", label="Introduction",
    )
    assert node.label == "Introduction"


def test_unified_edge_defaults():
    edge = UnifiedEdge(
        kind="CALLS", source_qualified="a::f", target_qualified="b::g", file_path="a.py",
    )
    assert edge.relation == "calls"
    assert edge.weight == 1.0
    assert edge.confidence == 1.0
    assert edge.confidence_tier == Confidence.EXTRACTED


def test_unified_edge_relation_override():
    edge = UnifiedEdge(
        kind="REFERENCES", source_qualified="a", target_qualified="b",
        file_path="x.py", relation="semantically_similar_to",
    )
    assert edge.relation == "semantically_similar_to"


def test_node_kind_enum():
    assert NodeKind.FILE == "File"
    assert NodeKind.DOCUMENT == "Document"
    assert NodeKind.ENDPOINT == "Endpoint"


def test_edge_kind_enum():
    assert EdgeKind.CALLS == "CALLS"
    assert EdgeKind.SEMANTICALLY_SIMILAR == "SEMANTICALLY_SIMILAR"


def test_pipeline_enum():
    assert Pipeline.CODE_GRAPH == "code_graph"
    assert Pipeline.GATHON_DOC == "gathon_doc"
    assert Pipeline.OPENAPI_YAML == "openapi_yaml"


def test_confidence_scores():
    assert CONFIDENCE_SCORES["EXTRACTED"] == 1.0
    assert CONFIDENCE_SCORES["INFERRED"] == 0.5
    assert CONFIDENCE_SCORES["AMBIGUOUS"] == 0.2
