"""Parse images — delegate to Claude subagents with vision.

Images are marked as IMAGE nodes with minimal extraction.
Actual vision parsing happens via Claude Code subagents (skill.md).
This parser only creates the root IMAGE node; subagents do the semantic extraction.
"""

from __future__ import annotations

from pathlib import Path

from gathon.schema import Confidence, FileType, UnifiedEdge, UnifiedNode


def parse_image(path: Path) -> tuple[list[UnifiedNode], list[UnifiedEdge]]:
    """Create IMAGE node. Vision parsing delegated to Claude subagents."""
    nodes = []
    edges = []

    root = UnifiedNode(
        kind="Image",
        name=path.stem,
        qualified_name=f"{path}::root",
        file_path=str(path),
        label=path.stem,
        file_type=FileType.IMAGE,
        confidence=Confidence.AMBIGUOUS,
        confidence_score=0.2,
        source_location=str(path),
        pipeline="gathon_image",
    )
    nodes.append(root)

    return nodes, edges
