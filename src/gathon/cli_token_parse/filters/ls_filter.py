"""Ls filter — compact directory listing with size + extension summary."""

from __future__ import annotations

import re
from collections import Counter

from gathon.cli_token_parse.engine import register

_DATE_RE = re.compile(
    r"\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
    r"\s+\d{1,2}\s+(?:\d{4}|\d{2}:\d{2})\s+",
)

_NOISE_DIRS = frozenset({
    "node_modules", ".git", "__pycache__", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", "target", "dist", "build", ".next", ".nuxt",
    ".tox", ".venv", "venv", ".eggs", "*.egg-info",
})


@register(r"^ls(?:\s|$)", "ls")
def filter_ls(stdout: str, stderr: str, args: list[str]) -> str:
    lines = stdout.splitlines()
    if not lines:
        return "(empty)\n"

    dirs: list[str] = []
    files: list[tuple[str, str]] = []
    ext_counter: Counter[str] = Counter()

    for line in lines:
        if line.startswith("total "):
            continue

        m = _DATE_RE.search(line)
        if not m:
            continue

        before = line[:m.start()]
        after = line[m.end():]
        name = after.strip()

        if not name or name in (".", ".."):
            continue

        if name.split("/")[0] in _NOISE_DIRS:
            continue

        size = _extract_size(before)
        file_type = line[0] if line else "-"

        if file_type == "d":
            dirs.append(f"{name}/")
        elif file_type == "l":
            files.append((name, size))
        else:
            files.append((name, size))
            ext = _get_extension(name)
            if ext:
                ext_counter[ext] += 1

    parts: list[str] = []
    for d in sorted(dirs):
        parts.append(d)
    for name, size in sorted(files):
        parts.append(f"  {name}  {size}")

    total_files = len(files)
    total_dirs = len(dirs)
    summary_parts = [f"{total_files} files", f"{total_dirs} dirs"]

    top_exts = ext_counter.most_common(5)
    if top_exts:
        ext_str = ", ".join(f"{c} {e}" for e, c in top_exts)
        summary_parts.append(ext_str)

    parts.append("")
    parts.append(f"Summary: {', '.join(summary_parts)}")

    return "\n".join(parts) + "\n"


def _extract_size(before_date: str) -> str:
    parts = before_date.split()
    for p in reversed(parts):
        if p.isdigit():
            return _human_size(int(p))
    return ""


def _human_size(n: int) -> str:
    if n < 1024:
        return f"{n}B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f}K"
    return f"{n / (1024 * 1024):.1f}M"


def _get_extension(name: str) -> str:
    if "." in name:
        ext = "." + name.rsplit(".", 1)[-1]
        if len(ext) <= 6:
            return ext
    return ""
