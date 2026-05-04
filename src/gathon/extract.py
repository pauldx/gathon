"""Orchestrator: route files to correct pipeline, extract, adapt, store."""

from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path
from typing import Any

from gathon.router import route_files
from gathon.schema import Pipeline
from gathon.store import UnifiedStore

logger = logging.getLogger(__name__)


def _hash_file(path: Path) -> tuple[bytes, str]:
    """Read file once, return (raw_bytes, sha256_hex)."""
    raw = path.read_bytes()
    return raw, hashlib.sha256(raw).hexdigest()


def _extract_code_graph(
    files: list[Path],
    store: UnifiedStore,
    repo_root: Path,
) -> dict[str, Any]:
    """Run CodeParser on code files, adapt results, store."""
    from gathon.code_graph.parser import CodeParser

    from gathon.adapters.code_graph import adapt_parse_result

    parser = CodeParser()
    stats = {"parsed": 0, "errors": []}

    for path in files:
        t0 = time.monotonic()
        try:
            raw, fhash = _hash_file(path)

            run = store.get_pipeline_run(str(path))
            if run and run["file_hash"] == fhash:
                continue

            nodes_raw, edges_raw = parser.parse_bytes(path, raw)
            nodes, edges = adapt_parse_result(nodes_raw, edges_raw, fhash)
            duration = int((time.monotonic() - t0) * 1000)

            store.store_unified_file(
                str(path), nodes, edges,
                file_hash=fhash,
                pipeline=Pipeline.CODE_GRAPH,
                duration_ms=duration,
            )
            stats["parsed"] += 1
        except Exception as exc:
            logger.warning("Parse failed: %s — %s", path, exc)
            stats["errors"].append({"file": str(path), "error": str(exc)})

    return stats


def _extract_gathon(
    files: list[Path],
    store: UnifiedStore,
    pipeline: str,
) -> dict[str, Any]:
    """Route gathon_* pipelines to built-in parsers."""
    import importlib

    parser_map = {
        Pipeline.GATHON_DOC: ("gathon.multimodal_graph.doc_parser", "parse_doc"),
        Pipeline.GATHON_PDF: ("gathon.multimodal_graph.pdf_parser", "parse_pdf"),
        Pipeline.GATHON_OFFICE: ("gathon.multimodal_graph.office_parser", "parse_office"),
        Pipeline.GATHON_IMAGE: ("gathon.multimodal_graph.image_parser", "parse_image"),
        Pipeline.GATHON_VIDEO: ("gathon.multimodal_graph.video_parser", "parse_video"),
    }

    if pipeline not in parser_map:
        return {"parsed": 0, "errors": [{"file": str(f), "error": f"Unknown pipeline: {pipeline}"} for f in files]}

    module_name, func_name = parser_map[pipeline]

    try:
        mod = importlib.import_module(module_name)
        parse_fn = getattr(mod, func_name)
    except (ImportError, AttributeError) as exc:
        logger.warning("Parser import failed for %s: %s", pipeline, exc)
        return {"parsed": 0, "errors": [{"file": str(f), "error": str(exc)} for f in files]}

    stats = {"parsed": 0, "errors": []}

    for path in files:
        t0 = time.monotonic()
        try:
            _, fhash = _hash_file(path)

            run = store.get_pipeline_run(str(path))
            if run and run["file_hash"] == fhash:
                continue

            nodes, edges = parse_fn(path)
            duration = int((time.monotonic() - t0) * 1000)

            store.store_unified_file(
                str(path), nodes, edges,
                file_hash=fhash,
                pipeline=pipeline,
                duration_ms=duration,
            )
            stats["parsed"] += 1
        except Exception as exc:
            logger.warning("Parser failed for %s: %s — %s", pipeline, path, exc)
            stats["errors"].append({"file": str(path), "error": str(exc)})

    return stats


def _extract_openapi(
    files: list[Path],
    store: UnifiedStore,
) -> dict[str, Any]:
    """Run OpenAPI parser on spec files."""
    from gathon.multimodal_graph.openapi_parser import parse_openapi

    stats = {"parsed": 0, "errors": []}

    for path in files:
        t0 = time.monotonic()
        try:
            _, fhash = _hash_file(path)

            run = store.get_pipeline_run(str(path))
            if run and run["file_hash"] == fhash:
                continue

            nodes, edges = parse_openapi(path)
            duration = int((time.monotonic() - t0) * 1000)

            store.store_unified_file(
                str(path), nodes, edges,
                file_hash=fhash,
                pipeline=Pipeline.OPENAPI_YAML,
                duration_ms=duration,
            )
            stats["parsed"] += 1
        except Exception as exc:
            logger.warning("OpenAPI parse failed: %s — %s", path, exc)
            stats["errors"].append({"file": str(path), "error": str(exc)})

    return stats


def _extract_config(
    files: list[Path],
    store: UnifiedStore,
) -> dict[str, Any]:
    """Run config parser on YAML/JSON/TOML files."""
    from gathon.multimodal_graph.config_parser import parse_config

    stats = {"parsed": 0, "errors": []}

    for path in files:
        t0 = time.monotonic()
        try:
            _, fhash = _hash_file(path)

            run = store.get_pipeline_run(str(path))
            if run and run["file_hash"] == fhash:
                continue

            nodes, edges = parse_config(path)
            duration = int((time.monotonic() - t0) * 1000)

            store.store_unified_file(
                str(path), nodes, edges,
                file_hash=fhash,
                pipeline=Pipeline.CONFIG_YAML,
                duration_ms=duration,
            )
            stats["parsed"] += 1
        except Exception as exc:
            logger.warning("Config parse failed: %s — %s", path, exc)
            stats["errors"].append({"file": str(path), "error": str(exc)})

    return stats


_GATHON_PIPELINES = {
    Pipeline.GATHON_DOC,
    Pipeline.GATHON_PDF,
    Pipeline.GATHON_OFFICE,
    Pipeline.GATHON_IMAGE,
    Pipeline.GATHON_VIDEO,
}


def extract_files(
    files: list[Path],
    store: UnifiedStore,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Route files to pipelines, extract, adapt, store. Returns summary."""
    if repo_root is None:
        repo_root = Path.cwd()

    groups = route_files(files)
    result: dict[str, Any] = {
        "total_files": len(files),
        "pipelines": {},
        "errors": [],
    }

    for pipeline, pipe_files in groups.items():
        if pipeline == Pipeline.CODE_GRAPH:
            stats = _extract_code_graph(pipe_files, store, repo_root)
        elif pipeline in _GATHON_PIPELINES:
            stats = _extract_gathon(pipe_files, store, pipeline)
        elif pipeline == Pipeline.OPENAPI_YAML:
            stats = _extract_openapi(pipe_files, store)
        elif pipeline == Pipeline.CONFIG_YAML:
            stats = _extract_config(pipe_files, store)
        else:
            stats = _extract_gathon(pipe_files, store, pipeline)

        result["pipelines"][pipeline] = {
            "files": len(pipe_files),
            "parsed": stats["parsed"],
            "errors": len(stats["errors"]),
        }
        result["errors"].extend(stats["errors"])

    store.commit()
    return result
