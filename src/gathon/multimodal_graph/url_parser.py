"""Parse URL content — fetch and route to appropriate parser."""

from __future__ import annotations

import ipaddress
import re
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen

from gathon.schema import Confidence, FileType, UnifiedEdge, UnifiedNode


def _validate_url(url: str) -> bool:
    """SSRF guard: reject private/metadata IPs."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False

        host = parsed.hostname
        if not host:
            return False

        try:
            ip = ipaddress.ip_address(host)
            return not (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_reserved
            )
        except ValueError:
            return True
    except Exception:
        return False


def parse_url(url: str) -> tuple[list[UnifiedNode], list[UnifiedEdge]]:
    """Fetch URL, detect type, route to parser."""
    if not _validate_url(url):
        return [], []

    nodes = []
    edges = []

    root = UnifiedNode(
        kind="Document",
        name=url[:50],
        qualified_name=f"url::{url}",
        file_path=url,
        label=url,
        file_type=FileType.DOCUMENT,
        confidence=Confidence.INFERRED,
        confidence_score=0.6,
        pipeline="gathon_url",
    )
    nodes.append(root)

    try:
        if "arxiv.org" in url:
            return _parse_arxiv(url, root, nodes, edges)
        elif url.endswith((".pdf", ".PDF")):
            return _parse_pdf_url(url, root, nodes, edges)
        elif any(url.endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".webp", ".gif"]):
            return _parse_image_url(url, root, nodes, edges)
        else:
            return _parse_webpage(url, root, nodes, edges)
    except Exception:
        return [root], []


def _parse_arxiv(
    url: str,
    root: UnifiedNode,
    nodes: list[UnifiedNode],
    edges: list[UnifiedEdge],
) -> tuple[list[UnifiedNode], list[UnifiedEdge]]:
    """Fetch arXiv abstract."""
    try:
        paper_id = re.search(r"arxiv\.org/abs/(\d+\.\d+)", url)
        if not paper_id:
            return [root], []

        abs_url = f"https://arxiv.org/abs/{paper_id.group(1)}"
        response = urlopen(abs_url, timeout=5)
        html = response.read().decode("utf-8", errors="replace")

        title_match = re.search(r"<meta name=\"citation_title\" content=\"([^\"]+)\"", html)
        abstract_match = re.search(r"<span class=\"abstract-text\">([^<]+)", html)

        if title_match:
            title_node = UnifiedNode(
                kind="Concept",
                name="title",
                qualified_name=f"{url}::title",
                file_path=url,
                label=title_match.group(1)[:100],
                file_type=FileType.PAPER,
                confidence=Confidence.EXTRACTED,
                confidence_score=0.95,
            )
            nodes.append(title_node)
            edges.append(UnifiedEdge(
                kind="CONTAINS",
                source_qualified=root.qualified_name,
                target_qualified=title_node.qualified_name,
                file_path=url,
                relation="contains",
                confidence=0.95,
            ))

        if abstract_match:
            abstract_node = UnifiedNode(
                kind="Section",
                name="abstract",
                qualified_name=f"{url}::abstract",
                file_path=url,
                label=abstract_match.group(1)[:100],
                file_type=FileType.PAPER,
                confidence=Confidence.EXTRACTED,
                confidence_score=0.95,
            )
            nodes.append(abstract_node)
            edges.append(UnifiedEdge(
                kind="CONTAINS",
                source_qualified=root.qualified_name,
                target_qualified=abstract_node.qualified_name,
                file_path=url,
                relation="contains",
                confidence=0.95,
            ))
    except Exception:
        pass

    return nodes, edges


def _parse_pdf_url(
    url: str,
    root: UnifiedNode,
    nodes: list[UnifiedNode],
    edges: list[UnifiedEdge],
) -> tuple[list[UnifiedNode], list[UnifiedEdge]]:
    """Download PDF URL, would need pypdf."""
    pdf_note = UnifiedNode(
        kind="Section",
        name="pdf_url",
        qualified_name=f"{url}::pdf",
        file_path=url,
        label="PDF file (download required)",
        file_type=FileType.PAPER,
        confidence=Confidence.AMBIGUOUS,
        confidence_score=0.2,
    )
    nodes.append(pdf_note)
    edges.append(UnifiedEdge(
        kind="CONTAINS",
        source_qualified=root.qualified_name,
        target_qualified=pdf_note.qualified_name,
        file_path=url,
        relation="contains",
        confidence=0.2,
    ))
    return nodes, edges


def _parse_image_url(
    url: str,
    root: UnifiedNode,
    nodes: list[UnifiedNode],
    edges: list[UnifiedEdge],
) -> tuple[list[UnifiedNode], list[UnifiedEdge]]:
    """Image URL would need download + vision."""
    image_note = UnifiedNode(
        kind="Image",
        name="image_url",
        qualified_name=f"{url}::image",
        file_path=url,
        label="Image file (vision analysis required)",
        file_type=FileType.IMAGE,
        confidence=Confidence.AMBIGUOUS,
        confidence_score=0.2,
    )
    nodes.append(image_note)
    edges.append(UnifiedEdge(
        kind="CONTAINS",
        source_qualified=root.qualified_name,
        target_qualified=image_note.qualified_name,
        file_path=url,
        relation="contains",
        confidence=0.2,
    ))
    return nodes, edges


def _parse_webpage(
    url: str,
    root: UnifiedNode,
    nodes: list[UnifiedNode],
    edges: list[UnifiedEdge],
) -> tuple[list[UnifiedNode], list[UnifiedEdge]]:
    """Fetch HTML, strip tags, treat as document."""
    try:
        response = urlopen(url, timeout=5)
        html = response.read().decode("utf-8", errors="replace")
    except Exception:
        return [root], []

    text = re.sub(r"<[^>]+>", "\n", html)
    paragraphs = re.split(r"\n\s*\n", text.strip())

    for i, para in enumerate(paragraphs[:5]):
        if not para.strip() or len(para) < 20:
            continue

        preview = para[:80].replace("\n", " ").strip()
        section = UnifiedNode(
            kind="Section",
            name=f"para_{i}",
            qualified_name=f"{url}::p_{i}",
            file_path=url,
            label=preview,
            file_type=FileType.DOCUMENT,
            confidence=Confidence.EXTRACTED,
            confidence_score=0.7,
        )
        nodes.append(section)

        edges.append(UnifiedEdge(
            kind="CONTAINS",
            source_qualified=root.qualified_name,
            target_qualified=section.qualified_name,
            file_path=url,
            relation="contains",
            confidence=0.7,
        ))

    return nodes, edges
