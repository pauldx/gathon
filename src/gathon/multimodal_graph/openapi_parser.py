"""Extract endpoints, schemas, and refs from OpenAPI spec files."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from gathon.schema import (
    Confidence,
    FileType,
    Pipeline,
    UnifiedEdge,
    UnifiedNode,
)

_HTTP_METHODS = {"get", "post", "put", "delete", "patch", "head", "options"}
_DOMAIN_RE = re.compile(r"^/([a-z][\w-]*)")


def _extract_refs(obj: Any, refs: set[str] | None = None) -> set[str]:
    """Recursively extract $ref schema names from nested dicts/lists."""
    if refs is None:
        refs = set()
    if isinstance(obj, dict):
        if "$ref" in obj:
            ref = obj["$ref"]
            if isinstance(ref, str) and ref.startswith(
                "#/components/schemas/"
            ):
                refs.add(ref.removeprefix("#/components/schemas/"))
        for v in obj.values():
            _extract_refs(v, refs)
    elif isinstance(obj, list):
        for item in obj:
            _extract_refs(item, refs)
    return refs


def _get_domain(path: str) -> str:
    m = _DOMAIN_RE.match(path)
    return m.group(1) if m else "other"


def parse_openapi(
    path: Path,
) -> tuple[list[UnifiedNode], list[UnifiedEdge]]:
    """Parse OpenAPI spec, produce Endpoint/APIResource nodes + edges."""
    text = path.read_text(errors="replace")
    spec = yaml.safe_load(text)
    if not isinstance(spec, dict):
        return [], []

    file_path = str(path)
    nodes: list[UnifiedNode] = []
    edges: list[UnifiedEdge] = []

    file_node = UnifiedNode(
        kind="ConfigFile",
        name=path.name,
        qualified_name=file_path,
        file_path=file_path,
        label=spec.get("info", {}).get("title", path.name),
        file_type=FileType.API_SPEC,
        confidence=Confidence.EXTRACTED,
        pipeline=Pipeline.OPENAPI_YAML,
    )
    nodes.append(file_node)

    schema_qns: dict[str, str] = {}
    for name, schema_def in (
        spec.get("components", {}).get("schemas", {}).items()
    ):
        qn = f"{file_path}::schema:{name}"
        schema_qns[name] = qn

        props = list(schema_def.get("properties", {}).keys())[:10]
        schema_type = schema_def.get("type", "object")
        label = f"{name} ({schema_type})"
        if props:
            label += f" [{', '.join(props)}]"

        nodes.append(UnifiedNode(
            kind="APIResource",
            name=name,
            qualified_name=qn,
            file_path=file_path,
            label=label,
            file_type=FileType.API_SPEC,
            confidence=Confidence.EXTRACTED,
            pipeline=Pipeline.OPENAPI_YAML,
        ))
        edges.append(UnifiedEdge(
            kind="CONTAINS",
            source_qualified=file_path,
            target_qualified=qn,
            file_path=file_path,
            relation="contains",
        ))

        for ref_name in _extract_refs(schema_def):
            if ref_name != name:
                edges.append(UnifiedEdge(
                    kind="REFERENCES",
                    source_qualified=qn,
                    target_qualified=f"{file_path}::schema:{ref_name}",
                    file_path=file_path,
                    relation="references",
                ))

    for url_path, path_item in (spec.get("paths") or {}).items():
        if not isinstance(path_item, dict):
            continue
        for method, details in path_item.items():
            if method not in _HTTP_METHODS or not isinstance(details, dict):
                continue

            summary = (
                details.get("summary")
                or details.get("operationId")
                or ""
            )
            tags = details.get("tags", [])
            qn = f"{file_path}::{method.upper()} {url_path}"

            label = f"{method.upper()} {url_path}"
            if summary:
                label += f" — {summary}"

            nodes.append(UnifiedNode(
                kind="Endpoint",
                name=f"{method.upper()} {url_path}",
                qualified_name=qn,
                file_path=file_path,
                label=label,
                file_type=FileType.API_SPEC,
                confidence=Confidence.EXTRACTED,
                pipeline=Pipeline.OPENAPI_YAML,
                extra={"tags": tags, "domain": _get_domain(url_path)},
            ))
            edges.append(UnifiedEdge(
                kind="CONTAINS",
                source_qualified=file_path,
                target_qualified=qn,
                file_path=file_path,
                relation="contains",
            ))

            refs = set()
            for section in ("requestBody", "responses", "parameters"):
                if section in details:
                    _extract_refs(details[section], refs)

            for ref_name in sorted(refs):
                ref_qn = schema_qns.get(
                    ref_name, f"{file_path}::schema:{ref_name}",
                )
                edges.append(UnifiedEdge(
                    kind="REFERENCES",
                    source_qualified=qn,
                    target_qualified=ref_qn,
                    file_path=file_path,
                    relation="references",
                ))

    return nodes, edges
