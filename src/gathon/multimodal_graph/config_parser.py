"""Extract key-hierarchy nodes from YAML, JSON, and TOML config files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from gathon.schema import (
    Confidence,
    FileType,
    Pipeline,
    UnifiedEdge,
    UnifiedNode,
)

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]

import yaml


def _walk_keys(
    data: Any,
    file_path: str,
    prefix: str = "",
    depth: int = 0,
    max_depth: int = 6,
) -> tuple[list[UnifiedNode], list[UnifiedEdge]]:
    """Recursively walk dict keys producing ConfigKey nodes + CONTAINS edges."""
    nodes: list[UnifiedNode] = []
    edges: list[UnifiedEdge] = []

    if not isinstance(data, dict) or depth > max_depth:
        return nodes, edges

    for key, value in data.items():
        qn = f"{prefix}.{key}" if prefix else key
        full_qn = f"{file_path}::{qn}"

        is_leaf = not isinstance(value, dict)
        node = UnifiedNode(
            kind="ConfigKey",
            name=key,
            qualified_name=full_qn,
            file_path=file_path,
            label=f"{qn} = {_preview(value)}" if is_leaf else qn,
            file_type=FileType.CONFIG,
            confidence=Confidence.EXTRACTED,
            confidence_score=1.0,
            pipeline=Pipeline.CONFIG_YAML,
        )
        nodes.append(node)

        if prefix:
            parent_qn = f"{file_path}::{prefix}"
            edges.append(UnifiedEdge(
                kind="CONTAINS",
                source_qualified=parent_qn,
                target_qualified=full_qn,
                file_path=file_path,
                relation="contains",
            ))

        if isinstance(value, dict):
            child_nodes, child_edges = _walk_keys(
                value, file_path, qn, depth + 1, max_depth,
            )
            nodes.extend(child_nodes)
            edges.extend(child_edges)

    return nodes, edges


def _preview(value: Any, max_len: int = 60) -> str:
    """Short string preview of a config value."""
    if isinstance(value, list):
        return f"[{len(value)} items]"
    s = str(value)
    return s if len(s) <= max_len else s[:max_len] + "..."


def parse_config(
    path: Path,
) -> tuple[list[UnifiedNode], list[UnifiedEdge]]:
    """Parse a config file and return unified nodes + edges."""
    text = path.read_text(errors="replace")
    ext = path.suffix.lower()
    file_path = str(path)

    if ext == ".toml":
        data = tomllib.loads(text)
    elif ext == ".json":
        data = json.loads(text)
    else:
        data = yaml.safe_load(text)

    if not isinstance(data, dict):
        return [], []

    file_node = UnifiedNode(
        kind="ConfigFile",
        name=path.name,
        qualified_name=file_path,
        file_path=file_path,
        label=path.name,
        file_type=FileType.CONFIG,
        confidence=Confidence.EXTRACTED,
        pipeline=Pipeline.CONFIG_YAML,
    )

    key_nodes, edges = _walk_keys(data, file_path)

    for node in key_nodes:
        if "." not in node.qualified_name.split("::")[-1]:
            edges.append(UnifiedEdge(
                kind="CONTAINS",
                source_qualified=file_path,
                target_qualified=node.qualified_name,
                file_path=file_path,
                relation="contains",
            ))

    return [file_node, *key_nodes], edges
