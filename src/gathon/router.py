"""Route files to the optimal extraction pipeline based on extension and content."""

from __future__ import annotations

from pathlib import Path

from gathon.schema import Pipeline

CODE_EXTENSIONS: frozenset[str] = frozenset({
    ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".go", ".rs", ".java",
    ".cs", ".rb", ".cpp", ".cc", ".cxx", ".c", ".h", ".hpp", ".kt",
    ".kts", ".swift", ".php", ".scala", ".lua", ".zig", ".ps1", ".ex",
    ".exs", ".jl", ".vue", ".svelte", ".dart", ".sh", ".bash", ".zsh",
    ".ksh", ".sol", ".gd", ".pl", ".pm", ".ipynb", ".r",
})

DOC_EXTENSIONS: frozenset[str] = frozenset({
    ".md", ".mdx", ".txt", ".rst", ".html",
})

PAPER_EXTENSIONS: frozenset[str] = frozenset({".pdf"})

OFFICE_EXTENSIONS: frozenset[str] = frozenset({".docx", ".xlsx"})

IMAGE_EXTENSIONS: frozenset[str] = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg",
})

VIDEO_EXTENSIONS: frozenset[str] = frozenset({
    ".mp4", ".mov", ".webm", ".mkv", ".avi", ".mp3", ".wav", ".m4a",
})

CONFIG_EXTENSIONS: frozenset[str] = frozenset({
    ".yaml", ".yml", ".json", ".toml",
})


def _is_openapi(path: Path) -> bool:
    """Heuristic: YAML/JSON file is OpenAPI if it contains openapi or swagger key."""
    try:
        head = path.read_text(errors="replace")[:2048]
        return "openapi:" in head or '"openapi"' in head or "swagger:" in head
    except OSError:
        return False


def route_file(path: Path) -> Pipeline:
    """Determine which pipeline should process a file."""
    ext = path.suffix.lower()

    if ext in CODE_EXTENSIONS:
        return Pipeline.CODE_GRAPH

    if ext in DOC_EXTENSIONS:
        return Pipeline.GATHON_DOC

    if ext in PAPER_EXTENSIONS:
        return Pipeline.GATHON_PDF

    if ext in OFFICE_EXTENSIONS:
        return Pipeline.GATHON_OFFICE

    if ext in IMAGE_EXTENSIONS:
        return Pipeline.GATHON_IMAGE

    if ext in VIDEO_EXTENSIONS:
        return Pipeline.GATHON_VIDEO

    if ext in CONFIG_EXTENSIONS:
        if _is_openapi(path):
            return Pipeline.OPENAPI_YAML
        return Pipeline.CONFIG_YAML

    return Pipeline.GATHON_DOC


def route_files(paths: list[Path]) -> dict[Pipeline, list[Path]]:
    """Batch route: group files by pipeline."""
    groups: dict[Pipeline, list[Path]] = {}
    for p in paths:
        pipe = route_file(p)
        groups.setdefault(pipe, []).append(p)
    return groups
