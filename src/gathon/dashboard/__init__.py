"""Gathon unified observability dashboard."""

from __future__ import annotations

import webbrowser
from pathlib import Path

from gathon.dashboard.aggregator import aggregate
from gathon.dashboard.renderer import render


def generate_dashboard(
    days: int = 7,
    repo_path: Path | None = None,
    out_path: Path | str | None = None,
) -> Path:
    if repo_path is None:
        repo_path = Path.cwd()
    repo_path = Path(repo_path).resolve()

    default_out = Path.home() / ".gathon" / "dashboard.html"
    out = Path(out_path).resolve() if out_path else default_out
    out.parent.mkdir(parents=True, exist_ok=True)

    data = aggregate(days=days, repo_path=repo_path)
    html = render(data)
    out.write_text(html, encoding="utf-8")
    return out
