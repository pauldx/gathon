"""Incremental updates: hash-based skip + git-diff targeted extraction."""

from __future__ import annotations

import hashlib
import logging
import re
import subprocess
from pathlib import Path
from typing import Any

from gathon.extract import extract_files
from gathon.store import UnifiedStore

logger = logging.getLogger(__name__)

_SAFE_GIT_REF = re.compile(r"^[\w./@^~{}\-]+$")

_IGNORE_DIRS = frozenset({
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    ".tox", ".mypy_cache", ".ruff_cache", ".pytest_cache",
    "dist", "build", ".next", ".nuxt",
})

_IGNORE_EXTENSIONS = frozenset({
    ".pyc", ".pyo", ".so", ".dylib", ".dll", ".exe",
    ".whl", ".egg", ".lock", ".map",
})


def collect_files(
    root: Path,
    follow_symlinks: bool = False,
) -> list[Path]:
    """Collect all processable files under root, respecting ignore rules."""
    files: list[Path] = []
    for entry in root.rglob("*"):
        if follow_symlinks:
            if not entry.is_file():
                continue
        else:
            if entry.is_symlink() or not entry.is_file():
                continue
        parts = entry.relative_to(root).parts
        if any(p in _IGNORE_DIRS for p in parts):
            continue
        if entry.suffix.lower() in _IGNORE_EXTENSIONS:
            continue
        if entry.name.startswith("."):
            continue
        files.append(entry)
    return sorted(files)


def get_changed_files(
    repo_root: Path,
    base: str = "HEAD~1",
) -> list[str]:
    """Get changed files via git diff. Returns relative paths."""
    if not _SAFE_GIT_REF.match(base):
        raise ValueError(f"Unsafe git ref: {base}")

    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", base],
            capture_output=True, text=True, cwd=repo_root,
            timeout=30,
        )
        if result.returncode == 0:
            return [
                f for f in result.stdout.strip().split("\n") if f
            ]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "--cached"],
            capture_output=True, text=True, cwd=repo_root,
            timeout=30,
        )
        if result.returncode == 0:
            return [
                f for f in result.stdout.strip().split("\n") if f
            ]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return []


def get_file_hash(path: Path) -> str:
    """SHA256 hash of file contents."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def full_build(
    repo_root: Path,
    store: UnifiedStore,
) -> dict[str, Any]:
    """Full graph build: collect all files, extract, store."""
    files = collect_files(repo_root)
    logger.info("Full build: %d files under %s", len(files), repo_root)

    existing = set(store.get_all_files())
    current = {str(f) for f in files}
    stale = existing - current
    for s in stale:
        store.remove_file_data(s)
    if stale:
        logger.info("Removed %d stale files", len(stale))
        store.commit()

    result = extract_files(files, store, repo_root)
    result["stale_removed"] = len(stale)
    return result


def incremental_update(
    repo_root: Path,
    store: UnifiedStore,
    base: str = "HEAD~1",
    changed_files: list[str] | None = None,
) -> dict[str, Any]:
    """Incremental update: only re-process changed files."""
    if changed_files is None:
        changed_files = get_changed_files(repo_root, base)

    if not changed_files:
        logger.info("No changed files detected")
        return {
            "files_updated": 0, "changed_files": [],
            "errors": [],
        }

    removed = 0
    to_extract: list[Path] = []

    for rel in changed_files:
        abs_path = repo_root / rel
        if not abs_path.exists():
            store.remove_file_data(str(abs_path))
            removed += 1
            continue

        fhash = get_file_hash(abs_path)
        run = store.get_pipeline_run(str(abs_path))
        if run and run["file_hash"] == fhash:
            continue

        to_extract.append(abs_path)

    if removed:
        store.commit()

    if not to_extract:
        logger.info("All changed files unchanged by hash")
        return {
            "files_updated": 0,
            "removed": removed,
            "changed_files": changed_files,
            "errors": [],
        }

    logger.info(
        "Incremental: %d changed, %d to re-extract, %d removed",
        len(changed_files), len(to_extract), removed,
    )

    result = extract_files(to_extract, store, repo_root)
    result["removed"] = removed
    result["changed_files"] = changed_files
    return result
