"""Smart chunking strategies for indexing diverse content types."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

_HEADER_RE = re.compile(r"^(#{1,4})\s+(.+)$", re.MULTILINE)
_FENCE_RE = re.compile(r"^(`{3,}|~{3,})", re.MULTILINE)


@dataclass
class Chunk:
    title: str
    content: str


def chunk_markdown(text: str, max_chunk: int = 4096) -> list[Chunk]:
    """Split markdown by headers, keeping code blocks atomic."""
    if not text.strip():
        return []

    # Find all code fence boundaries so we never split inside one
    fence_ranges: list[tuple[int, int]] = []
    fence_stack: int | None = None
    for m in _FENCE_RE.finditer(text):
        if fence_stack is None:
            fence_stack = m.start()
        else:
            fence_ranges.append((fence_stack, m.end()))
            fence_stack = None

    def _in_fence(pos: int) -> bool:
        return any(start <= pos <= end for start, end in fence_ranges)

    # Collect header split points
    split_points: list[tuple[int, str]] = []
    for m in _HEADER_RE.finditer(text):
        if not _in_fence(m.start()):
            split_points.append((m.start(), m.group(2).strip()))

    if not split_points:
        return _chunk_by_paragraphs(text, max_chunk, "Section")

    chunks: list[Chunk] = []

    # Content before first header
    if split_points[0][0] > 0:
        preamble = text[: split_points[0][0]].strip()
        if preamble:
            chunks.extend(_split_oversized(Chunk("Preamble", preamble), max_chunk))

    for i, (pos, title) in enumerate(split_points):
        end = split_points[i + 1][0] if i + 1 < len(split_points) else len(text)
        body = text[pos:end].strip()
        if body:
            chunks.extend(_split_oversized(Chunk(title, body), max_chunk))

    return chunks


def chunk_plaintext(text: str, max_chunk: int = 4096) -> list[Chunk]:
    """Split plain text on paragraph breaks, fall back to line groups."""
    if not text.strip():
        return []

    paragraphs = re.split(r"\n\s*\n", text)
    paragraphs = [p.strip() for p in paragraphs if p.strip()]

    if len(paragraphs) < 3:
        return _chunk_by_lines(text, max_chunk)

    return _chunk_by_paragraphs(text, max_chunk, "Paragraph")


def chunk_json(data: dict | list, max_chunk: int = 4096) -> list[Chunk]:
    """Recursive tree walk with key paths as titles and array batching."""
    chunks: list[Chunk] = []
    _walk_json(data, "", chunks, max_chunk)
    return chunks


def _walk_json(
    data: dict | list | str | int | float | bool | None,
    path: str,
    chunks: list[Chunk],
    max_chunk: int,
) -> None:
    """Recursively walk JSON, emitting chunks at leaf/batch boundaries."""
    if isinstance(data, dict):
        # Try to find an identity field for labeling
        identity = None
        for key in ("id", "name", "title", "label"):
            if key in data and isinstance(data[key], (str, int)):
                identity = str(data[key])
                break

        serialized = json.dumps(data, default=str, ensure_ascii=False)
        if len(serialized) <= max_chunk:
            title = f"{path} ({identity})" if identity else (path or "root")
            chunks.append(Chunk(title, serialized))
            return

        for key, value in data.items():
            child_path = f"{path}.{key}" if path else key
            _walk_json(value, child_path, chunks, max_chunk)

    elif isinstance(data, list):
        # Batch array elements by serialized size
        batch: list = []
        batch_size = 0
        batch_start = 0

        for i, item in enumerate(data):
            item_str = json.dumps(item, default=str, ensure_ascii=False)
            if batch_size + len(item_str) > max_chunk and batch:
                title = f"{path}[{batch_start}..{i - 1}]"
                chunks.append(Chunk(title, json.dumps(batch, default=str, ensure_ascii=False)))
                batch = []
                batch_size = 0
                batch_start = i

            if len(item_str) > max_chunk:
                # Single item too large, recurse into it
                _walk_json(item, f"{path}[{i}]", chunks, max_chunk)
                batch_start = i + 1
            else:
                batch.append(item)
                batch_size += len(item_str)

        if batch:
            end_idx = batch_start + len(batch) - 1
            if len(batch) > 1:
                title = f"{path}[{batch_start}..{end_idx}]"
            else:
                title = f"{path}[{batch_start}]"
            chunks.append(Chunk(title, json.dumps(batch, default=str, ensure_ascii=False)))

    else:
        # Scalar leaf
        title = path or "value"
        chunks.append(Chunk(title, str(data)))


def _chunk_by_paragraphs(text: str, max_chunk: int, prefix: str) -> list[Chunk]:
    """Split text into paragraph-based chunks."""
    paragraphs = re.split(r"\n\s*\n", text)
    paragraphs = [p.strip() for p in paragraphs if p.strip()]

    chunks: list[Chunk] = []
    current = ""
    idx = 1

    for para in paragraphs:
        if len(current) + len(para) + 2 > max_chunk and current:
            chunks.append(Chunk(f"{prefix} {idx}", current))
            idx += 1
            current = para
        else:
            current = f"{current}\n\n{para}" if current else para

    if current:
        chunks.append(Chunk(f"{prefix} {idx}", current))

    return chunks


def _chunk_by_lines(text: str, max_chunk: int) -> list[Chunk]:
    """Fixed 20-line groups with 2-line overlap."""
    lines = text.splitlines()
    chunks: list[Chunk] = []
    group_size = 20
    overlap = 2
    idx = 1
    i = 0

    while i < len(lines):
        group = lines[i : i + group_size]
        content = "\n".join(group)

        if len(content) > max_chunk:
            # Further split this group at max_chunk boundary
            while content:
                chunks.append(Chunk(f"Lines {idx}", content[:max_chunk]))
                content = content[max_chunk:]
                idx += 1
        else:
            chunks.append(Chunk(f"Lines {idx}", content))
            idx += 1

        i += group_size - overlap

    return chunks


def _split_oversized(chunk: Chunk, max_chunk: int) -> list[Chunk]:
    """Split a single chunk if it exceeds max_chunk."""
    if len(chunk.content) <= max_chunk:
        return [chunk]

    parts: list[Chunk] = []
    remaining = chunk.content
    idx = 1

    while remaining:
        # Try to split at a paragraph break within limit
        segment = remaining[:max_chunk]
        if len(remaining) > max_chunk:
            last_break = segment.rfind("\n\n")
            if last_break > max_chunk // 4:
                segment = remaining[:last_break]

        title = f"{chunk.title} (part {idx})" if idx > 1 else chunk.title
        parts.append(Chunk(title, segment.strip()))
        remaining = remaining[len(segment):].strip()
        idx += 1

    return parts
