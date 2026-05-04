"""Parse PDF files into page sections."""

from __future__ import annotations

from pathlib import Path

from gathon.schema import Confidence, FileType, UnifiedEdge, UnifiedNode


def parse_pdf(path: Path) -> tuple[list[UnifiedNode], list[UnifiedEdge]]:
    """Parse PDF → page sections. Requires pypdf."""
    try:
        import pypdf
    except ImportError:
        return [], []

    nodes = []
    edges = []

    root = UnifiedNode(
        kind="Document",
        name=path.stem,
        qualified_name=f"{path}::root",
        file_path=str(path),
        label=path.stem,
        file_type=FileType.PAPER,
        confidence=Confidence.EXTRACTED,
        confidence_score=1.0,
        pipeline="gathon_pdf",
    )
    nodes.append(root)

    try:
        reader = pypdf.PdfReader(path)
    except Exception:
        return [root], []

    for i, page in enumerate(reader.pages[:50]):
        try:
            text = page.extract_text()[:200] if hasattr(page, "extract_text") else f"Page {i+1}"
        except Exception:
            text = f"Page {i+1}"

        section = UnifiedNode(
            kind="Section",
            name=f"page_{i+1}",
            qualified_name=f"{path}::page_{i+1}",
            file_path=str(path),
            label=f"Page {i+1}: {text[:50].replace(chr(10), ' ')}",
            file_type=FileType.PAPER,
            confidence=Confidence.EXTRACTED,
            confidence_score=1.0,
            line_start=i + 1,
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

    return nodes, edges
