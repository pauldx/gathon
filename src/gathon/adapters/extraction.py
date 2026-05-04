"""Adapt extraction dicts to UnifiedNode/UnifiedEdge."""

from __future__ import annotations

from typing import Any

from gathon.schema import (
    CONFIDENCE_SCORES,
    Confidence,
    FileType,
    Pipeline,
    UnifiedEdge,
    UnifiedNode,
)

_FILE_TYPE_MAP: dict[str, str] = {
    "code": FileType.CODE,
    "document": FileType.DOCUMENT,
    "paper": FileType.PAPER,
    "image": FileType.IMAGE,
    "video": FileType.VIDEO,
}

_RELATION_TO_KIND: dict[str, str] = {
    "contains": "CONTAINS",
    "method": "CONTAINS",
    "inherits": "INHERITS",
    "imports": "IMPORTS_FROM",
    "imports_from": "IMPORTS_FROM",
    "calls": "CALLS",
    "semantically_similar_to": "SEMANTICALLY_SIMILAR",
    "defines": "CONTAINS",
    "uses": "REFERENCES",
}


def _node_kind_from_file_type(file_type: str) -> str:
    if file_type == "code":
        return "Function"
    if file_type == "document":
        return "Section"
    if file_type == "paper":
        return "Document"
    if file_type == "image":
        return "Image"
    if file_type == "video":
        return "Video"
    return "Concept"


def adapt_node(raw: dict[str, Any], pipeline: str = "") -> UnifiedNode:
    """Convert node dict to UnifiedNode."""
    file_type = raw.get("file_type", "document")
    source_file = raw.get("source_file", "")
    node_id = raw.get("id", "")
    label = raw.get("label", node_id)

    qn = f"{source_file}::{node_id}" if source_file else node_id

    confidence_str = raw.get("confidence", Confidence.EXTRACTED)
    confidence_score = CONFIDENCE_SCORES.get(confidence_str, 1.0)

    return UnifiedNode(
        kind=_node_kind_from_file_type(file_type),
        name=node_id,
        qualified_name=qn,
        file_path=source_file,
        label=label,
        file_type=_FILE_TYPE_MAP.get(file_type, file_type),
        source_location=raw.get("source_location", ""),
        confidence=confidence_str,
        confidence_score=confidence_score,
        pipeline=pipeline or Pipeline.GATHON_DOC,
    )


def adapt_edge(raw: dict[str, Any]) -> UnifiedEdge:
    """Convert edge dict to UnifiedEdge."""
    relation = raw.get("relation", "references")
    confidence_str = raw.get("confidence", Confidence.EXTRACTED)
    confidence_score = CONFIDENCE_SCORES.get(confidence_str, 1.0)

    return UnifiedEdge(
        kind=_RELATION_TO_KIND.get(relation, "REFERENCES"),
        source_qualified=raw.get("source", ""),
        target_qualified=raw.get("target", ""),
        file_path=raw.get("source_file", ""),
        confidence=confidence_score,
        confidence_tier=confidence_str,
        relation=relation,
        weight=raw.get("weight", 1.0),
    )


def adapt_extraction(
    data: dict[str, Any],
    pipeline: str = "",
) -> tuple[list[UnifiedNode], list[UnifiedEdge]]:
    """Convert full extraction result to unified format."""
    nodes = [adapt_node(n, pipeline) for n in data.get("nodes", [])]
    edges = [adapt_edge(e) for e in data.get("edges", data.get("links", []))]
    return nodes, edges
