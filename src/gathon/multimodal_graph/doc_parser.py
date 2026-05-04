"""Parse markdown, text, rst, html documents into section hierarchy."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from gathon.schema import Confidence, FileType, UnifiedEdge, UnifiedNode


def _is_paper(text: str) -> bool:
    """Heuristic: text looks like academic paper."""
    head = text[:3000].lower()
    paper_markers = [
        "arxiv", "doi:", "abstract", "proceedings", "journal",
        "preprint", "\\cite{", "literature", "we propose",
        "research", "methodology", "conclusion", "references"
    ]
    matches = sum(1 for m in paper_markers if m in head)
    return matches >= 3


def parse_doc(path: Path) -> tuple[list[UnifiedNode], list[UnifiedEdge]]:
    """Parse .md/.txt/.rst/.html → section hierarchy."""
    nodes = []
    edges = []

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return [], []

    file_type = FileType.PAPER if _is_paper(text) else FileType.DOCUMENT

    root = UnifiedNode(
        kind="Document",
        name=path.stem,
        qualified_name=f"{path}::root",
        file_path=str(path),
        label=path.stem,
        file_type=file_type,
        confidence=Confidence.EXTRACTED,
        confidence_score=1.0,
        pipeline="gathon_doc",
    )
    nodes.append(root)

    ext = path.suffix.lower()

    if ext in {".md", ".mdx"}:
        _parse_markdown(text, path, root, nodes, edges)
    elif ext == ".html":
        _parse_html(text, path, root, nodes, edges)
    else:
        _parse_text(text, path, root, nodes, edges)

    return nodes, edges


def _parse_markdown(
    text: str,
    path: Path,
    root: UnifiedNode,
    nodes: list[UnifiedNode],
    edges: list[UnifiedEdge],
) -> None:
    """Parse ATX headings into section hierarchy."""
    lines = text.split("\n")
    stack: list[tuple[int, UnifiedNode]] = [(0, root)]

    for line in lines:
        match = re.match(r"^(#+)\s+(.+)$", line)
        if not match:
            continue

        level = len(match.group(1))
        title = match.group(2).strip()

        section = UnifiedNode(
            kind="Section",
            name=title[:50],
            qualified_name=f"{path}::section_{len(nodes)}",
            file_path=str(path),
            label=title,
            file_type=FileType.DOCUMENT,
            confidence=Confidence.EXTRACTED,
            confidence_score=1.0,
        )
        nodes.append(section)

        while len(stack) > 1 and stack[-1][0] >= level:
            stack.pop()

        parent = stack[-1][1]
        edges.append(UnifiedEdge(
            kind="CONTAINS",
            source_qualified=parent.qualified_name,
            target_qualified=section.qualified_name,
            file_path=str(path),
            relation="contains",
            confidence=1.0,
        ))

        stack.append((level, section))


def _parse_html(
    text: str,
    path: Path,
    root: UnifiedNode,
    nodes: list[UnifiedNode],
    edges: list[UnifiedEdge],
) -> None:
    """Strip HTML tags, treat as text."""
    text_clean = re.sub(r"<[^>]+>", "\n", text)
    _parse_text(text_clean, path, root, nodes, edges)


def _parse_text(
    text: str,
    path: Path,
    root: UnifiedNode,
    nodes: list[UnifiedNode],
    edges: list[UnifiedEdge],
) -> None:
    """Chunk text by paragraphs (blank lines)."""
    paragraphs = re.split(r"\n\s*\n", text.strip())

    for i, para in enumerate(paragraphs[:20]):
        if not para.strip() or len(para) < 10:
            continue

        preview = para[:100].replace("\n", " ").strip()
        section = UnifiedNode(
            kind="Section",
            name=f"paragraph_{i}",
            qualified_name=f"{path}::p_{i}",
            file_path=str(path),
            label=preview,
            file_type=FileType.DOCUMENT,
            confidence=Confidence.EXTRACTED,
            confidence_score=1.0,
        )
        nodes.append(section)

        edges.append(UnifiedEdge(
            kind="CONTAINS",
            source_qualified=root.qualified_name,
            target_qualified=section.qualified_name,
            file_path=str(path),
            relation="contains",
            confidence=1.0,
        ))
