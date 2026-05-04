"""Adapt NodeInfo/EdgeInfo to UnifiedNode/UnifiedEdge."""

from __future__ import annotations

from gathon.code_graph.parser import EdgeInfo, NodeInfo

from gathon.schema import (
    Confidence,
    FileType,
    Pipeline,
    UnifiedEdge,
    UnifiedNode,
)

_KIND_MAP: dict[str, str] = {
    "File": "File",
    "Class": "Class",
    "Function": "Function",
    "Test": "Test",
    "Type": "Type",
}


def adapt_node(node: NodeInfo, file_hash: str = "") -> UnifiedNode:
    """Convert NodeInfo to UnifiedNode."""
    qn = f"{node.file_path}::{node.name}"
    if node.parent_name:
        qn = f"{node.file_path}::{node.parent_name}.{node.name}"

    return UnifiedNode(
        kind=_KIND_MAP.get(node.kind, node.kind),
        name=node.name,
        qualified_name=qn,
        file_path=node.file_path,
        line_start=node.line_start,
        line_end=node.line_end,
        language=node.language,
        parent_name=node.parent_name,
        params=node.params,
        return_type=node.return_type,
        modifiers=node.modifiers,
        is_test=node.is_test,
        extra=node.extra,
        label=node.name,
        file_type=FileType.CODE,
        confidence=Confidence.EXTRACTED,
        confidence_score=1.0,
        pipeline=Pipeline.CODE_GRAPH,
    )


def adapt_edge(edge: EdgeInfo) -> UnifiedEdge:
    """Convert EdgeInfo to UnifiedEdge."""
    return UnifiedEdge(
        kind=edge.kind,
        source_qualified=edge.source,
        target_qualified=edge.target,
        file_path=edge.file_path,
        line=edge.line,
        extra=edge.extra,
        confidence=1.0,
        confidence_tier=Confidence.EXTRACTED,
        relation=edge.kind.lower(),
        weight=1.0,
    )


def adapt_parse_result(
    nodes: list[NodeInfo],
    edges: list[EdgeInfo],
    file_hash: str = "",
) -> tuple[list[UnifiedNode], list[UnifiedEdge]]:
    """Convert full parse output to unified format."""
    return (
        [adapt_node(n, file_hash) for n in nodes],
        [adapt_edge(e) for e in edges],
    )
