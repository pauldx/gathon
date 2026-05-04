"""Tests for gathon.adapters — format conversion."""

from gathon.code_graph.parser import EdgeInfo, NodeInfo

from gathon.adapters.code_graph import adapt_edge, adapt_node, adapt_parse_result
from gathon.adapters.extraction import adapt_extraction
from gathon.adapters.extraction import adapt_node as adapt_extraction_node
from gathon.schema import Confidence, FileType, Pipeline


class TestCodeGraphAdapter:
    def test_adapt_node_basic(self):
        ni = NodeInfo(
            kind="Function", name="hello", file_path="a.py",
            line_start=1, line_end=5, language="python",
        )
        node = adapt_node(ni)
        assert node.kind == "Function"
        assert node.name == "hello"
        assert node.qualified_name == "a.py::hello"
        assert node.file_type == FileType.CODE
        assert node.pipeline == Pipeline.CODE_GRAPH
        assert node.confidence == Confidence.EXTRACTED

    def test_adapt_node_with_parent(self):
        ni = NodeInfo(
            kind="Function", name="method", file_path="a.py",
            line_start=10, line_end=20, language="python",
            parent_name="MyClass",
        )
        node = adapt_node(ni)
        assert node.qualified_name == "a.py::MyClass.method"

    def test_adapt_edge(self):
        ei = EdgeInfo(
            kind="CALLS", source="a.py::f", target="b.py::g",
            file_path="a.py", line=5,
        )
        edge = adapt_edge(ei)
        assert edge.kind == "CALLS"
        assert edge.source_qualified == "a.py::f"
        assert edge.target_qualified == "b.py::g"
        assert edge.relation == "calls"
        assert edge.confidence == 1.0

    def test_adapt_parse_result(self):
        nodes_in = [
            NodeInfo(kind="File", name="a.py", file_path="a.py", line_start=0, line_end=100),
            NodeInfo(kind="Function", name="f", file_path="a.py", line_start=1, line_end=5),
        ]
        edges_in = [
            EdgeInfo(kind="CONTAINS", source="a.py", target="a.py::f", file_path="a.py"),
        ]
        nodes, edges = adapt_parse_result(nodes_in, edges_in)
        assert len(nodes) == 2
        assert len(edges) == 1
        assert all(n.pipeline == Pipeline.CODE_GRAPH for n in nodes)


class TestExtractionAdapter:
    def test_adapt_node_document(self):
        raw = {
            "id": "readme_intro",
            "label": "Introduction",
            "file_type": "document",
            "source_file": "README.md",
            "source_location": "L1",
        }
        node = adapt_extraction_node(raw)
        assert node.kind == "Section"
        assert node.name == "readme_intro"
        assert node.qualified_name == "README.md::readme_intro"
        assert node.label == "Introduction"
        assert node.file_type == FileType.DOCUMENT

    def test_adapt_node_code(self):
        raw = {
            "id": "utils_parse", "label": "parse",
            "file_type": "code", "source_file": "utils.py",
        }
        node = adapt_extraction_node(raw)
        assert node.kind == "Function"

    def test_adapt_node_image(self):
        raw = {
            "id": "arch_diagram", "label": "Architecture",
            "file_type": "image", "source_file": "arch.png",
        }
        node = adapt_extraction_node(raw)
        assert node.kind == "Image"

    def test_adapt_extraction(self):
        data = {
            "nodes": [
                {"id": "a", "label": "A", "file_type": "document", "source_file": "doc.md"},
                {"id": "b", "label": "B", "file_type": "document", "source_file": "doc.md"},
            ],
            "edges": [
                {"source": "a", "target": "b", "relation": "contains", "source_file": "doc.md"},
            ],
        }
        nodes, edges = adapt_extraction(data)
        assert len(nodes) == 2
        assert len(edges) == 1
        assert edges[0].kind == "CONTAINS"
        assert edges[0].relation == "contains"

    def test_adapt_extraction_with_links_key(self):
        data = {
            "nodes": [{"id": "x", "label": "X", "file_type": "code", "source_file": "x.py"}],
            "links": [
                {"source": "x", "target": "y", "relation": "calls", "source_file": "x.py"},
            ],
        }
        nodes, edges = adapt_extraction(data)
        assert len(edges) == 1

    def test_confidence_mapping(self):
        raw = {
            "id": "n", "label": "N", "file_type": "document",
            "source_file": "d.md", "confidence": "INFERRED",
        }
        node = adapt_extraction_node(raw)
        assert node.confidence == "INFERRED"
        assert node.confidence_score == 0.5
