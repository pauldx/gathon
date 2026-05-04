"""CLI entry point: gathon build|update|serve|status|export|install|dashboard."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click


@click.group()
@click.version_option(package_name="gathon")
def cli() -> None:
    """গাঁথন — Unified adaptive knowledge graph engine."""


@cli.command()
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--full", is_flag=True, help="Full rebuild (not incremental)")
@click.option("--base", default="HEAD~1", help="Git base ref for incremental")
@click.option(
    "--compress", default="off",
    type=click.Choice(["off", "lite", "full", "ultra"]),
    help="Compress stored text in doc nodes",
)
def build(path: str, full: bool, base: str, compress: str) -> None:
    """Build or update unified graph for a repo."""
    from gathon.incremental import full_build, incremental_update
    from gathon.store import UnifiedStore

    root = Path(path).resolve()
    db_dir = root / ".gathon"
    db_dir.mkdir(parents=True, exist_ok=True)
    store = UnifiedStore(str(db_dir / "graph.db"), compress_intensity=compress)

    try:
        if full:
            click.echo(f"Full build: {root}")
            result = full_build(root, store)
        else:
            click.echo(f"Incremental update: {root}")
            result = incremental_update(root, store, base=base)

        stats = store.get_unified_stats()
        click.echo(
            f"Done: {stats['total_nodes']} nodes, "
            f"{stats['total_edges']} edges, "
            f"{stats['files_count']} files"
        )
        if result.get("errors"):
            click.echo(
                f"Errors: {len(result['errors'])}", err=True,
            )
    finally:
        store.close()


@cli.command()
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--base", default="HEAD~1", help="Git base ref")
def update(path: str, base: str) -> None:
    """Incremental update (alias for build without --full)."""
    from gathon.incremental import incremental_update
    from gathon.store import UnifiedStore

    root = Path(path).resolve()
    db = root / ".gathon" / "graph.db"
    if not db.exists():
        click.echo("No graph.db found. Run 'gathon build' first.", err=True)
        sys.exit(1)

    store = UnifiedStore(str(db))
    try:
        result = incremental_update(root, store, base=base)
        click.echo(f"Updated {result.get('total_files', 0)} files")
    finally:
        store.close()


@cli.command()
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--transport", default="stdio", type=click.Choice(["stdio"]))
@click.option(
    "--compress", default="off",
    type=click.Choice(["off", "lite", "full", "ultra"]),
    help="Compress tool responses",
)
def serve(path: str, transport: str, compress: str) -> None:
    """Start MCP server."""
    from gathon.server import run, set_compression
    set_compression(compress)
    run(repo_root=str(Path(path).resolve()), transport=transport)


@cli.command()
@click.argument("path", default=".", type=click.Path(exists=True))
def status(path: str) -> None:
    """Show graph stats."""
    from gathon.store import UnifiedStore

    root = Path(path).resolve()
    db = root / ".gathon" / "graph.db"
    if not db.exists():
        click.echo("No graph found. Run 'gathon build' first.")
        return

    store = UnifiedStore(str(db))
    try:
        stats = store.get_unified_stats()
        click.echo(f"Nodes: {stats['total_nodes']}")
        click.echo(f"Edges: {stats['total_edges']}")
        click.echo(f"Files: {stats['files_count']}")
        click.echo(f"Languages: {', '.join(stats['languages'])}")
        click.echo(f"By kind: {json.dumps(stats['nodes_by_kind'])}")
        click.echo(
            f"By pipeline: {json.dumps(stats['nodes_by_pipeline'])}"
        )
        click.echo(
            f"By type: {json.dumps(stats['nodes_by_file_type'])}"
        )
    finally:
        store.close()


@cli.command()
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--days", default=7, help="Days for trend data")
def compression(path: str, days: int) -> None:
    """Show compression telemetry stats."""
    import sqlite3

    from gathon.telemetry import TelemetryStats

    root = Path(path).resolve()
    db = root / ".gathon" / "graph.db"
    if not db.exists():
        click.echo("No graph found. Run 'gathon build' first.", err=True)
        sys.exit(1)

    conn = sqlite3.connect(str(db))
    try:
        stats = TelemetryStats(conn)
        full = stats.get_full_stats(days)

        s = full["summary"]
        click.echo(f"Compression events: {s['total_events']}")
        click.echo(f"Total savings: {s['total_savings_tokens']} tokens "
                    f"({s['avg_savings_pct']}% avg)")
        click.echo(f"Before: {s['total_before_tokens']} → "
                    f"After: {s['total_after_tokens']}")

        if full["by_tool"]:
            click.echo("\nBy tool:")
            for t in full["by_tool"]:
                click.echo(f"  {t['tool']}: {t['savings_tokens']} saved "
                           f"({t['avg_savings_pct']}% avg, {t['events']} events)")

        if full["by_intensity"]:
            click.echo("\nBy intensity:")
            for i in full["by_intensity"]:
                click.echo(f"  {i['intensity']}: {i['savings_tokens']} saved "
                           f"({i['avg_savings_pct']}% avg)")

        d = full["disclosure"]
        if d["total_queries"] > 0:
            click.echo(f"\nDisclosure: {d['index_queries']} index, "
                       f"{d['full_queries']} full "
                       f"({d['upgrade_rate_pct']}% upgrade rate)")

        if full["trend"]:
            click.echo(f"\nTrend (last {days} days):")
            for day in full["trend"]:
                click.echo(f"  {day['date']}: {day['savings_tokens']} saved "
                           f"({day['events']} events)")
    finally:
        conn.close()


@cli.command(name="export")
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option(
    "--format", "fmt",
    default="json",
    type=click.Choice(["json", "html", "obsidian", "graphml", "svg"]),
)
@click.option("--output", "-o", default=None, help="Output path")
def export_cmd(path: str, fmt: str, output: str | None) -> None:
    """Export graph in various formats."""
    from gathon.export import export_unified
    from gathon.store import UnifiedStore

    root = Path(path).resolve()
    db = root / ".gathon" / "graph.db"
    if not db.exists():
        click.echo("No graph found. Run 'gathon build' first.", err=True)
        sys.exit(1)

    if output is None:
        output = str(root / ".gathon" / f"graph.{fmt}")

    store = UnifiedStore(str(db))
    try:
        result = export_unified(store, output, fmt)
        click.echo(f"Exported to {result['output']}: "
                    f"{result['nodes']} nodes, {result['edges']} edges")
    finally:
        store.close()


@cli.command()
@click.argument("path", default=".", type=click.Path(exists=True))
def install(path: str) -> None:
    """Install hooks and skill files for Claude Code."""
    from gathon.hooks import install_hooks

    root = Path(path).resolve()
    result = install_hooks(root)
    for msg in result.get("messages", []):
        click.echo(msg)
    click.echo("Install complete.")


# === CTP Commands ===


@cli.command(
    name="ctp",
    context_settings={"ignore_unknown_options": True},
)
@click.argument("command", nargs=-1, type=click.UNPROCESSED)
def ctp_cmd(command: tuple[str, ...]) -> None:
    """Run a command through CLI token parse output filter."""
    from gathon.cli_token_parse.engine import filter_command, load_filters

    load_filters()
    cmd_str = " ".join(command)
    if not cmd_str:
        click.echo("Usage: gathon ctp <command>", err=True)
        sys.exit(1)

    result = filter_command(cmd_str)
    click.echo(result.output, nl=False)
    sys.exit(result.exit_code)


@cli.command(name="ctp-init")
@click.option("--uninstall", is_flag=True, help="Remove the hook")
def ctp_init(uninstall: bool) -> None:
    """Install/uninstall CLI token parse PreToolUse hook for Claude Code."""
    from gathon.cli_token_parse.hook import install_hook, uninstall_hook

    if uninstall:
        uninstall_hook()
    else:
        install_hook()


@cli.command(name="ctp-hook")
def ctp_hook() -> None:
    """PreToolUse hook entry point (called by Claude Code)."""
    from gathon.cli_token_parse.hook import hook_main

    hook_main()


@cli.command(name="ctp-gain")
@click.option("--history", "-H", is_flag=True, help="Recent commands")
@click.option("--days", default=7, help="Days for trend")
def ctp_gain(history: bool, days: int) -> None:
    """Show CLI token parse filter token savings."""
    from gathon.cli_token_parse.telemetry import CtpTelemetryDB

    db = CtpTelemetryDB()
    try:
        if history:
            entries = db.get_history()
            if not entries:
                click.echo("No CTP commands tracked yet.")
                return
            click.echo("Recent CTP commands:")
            for e in entries:
                click.echo(f"  [{e['filter']}] {e['command'][:60]} "
                           f"— {e['pct']}% saved ({e['ms']:.0f}ms)")
            return

        s = db.get_summary()
        click.echo("CTP Token Savings")
        click.echo(f"{'=' * 50}")
        click.echo(f"Commands:  {s['total_commands']}")
        click.echo(f"Before:    {s['total_before']} tokens")
        click.echo(f"After:     {s['total_after']} tokens")
        click.echo(f"Saved:     {s['total_savings']} tokens "
                   f"({s['avg_savings_pct']}% avg)")
        click.echo(f"Avg time:  {s['avg_elapsed_ms']}ms")

        by_filter = db.get_by_filter()
        if by_filter:
            click.echo("\nBy filter:")
            for f in by_filter:
                click.echo(f"  {f['filter']}: {f['savings']} saved "
                           f"({f['avg_pct']}% avg, {f['count']} cmds, "
                           f"{f['avg_ms']:.0f}ms)")

        trend = db.get_trend(days)
        if trend:
            click.echo(f"\nTrend (last {days} days):")
            for t in trend:
                click.echo(f"  {t['date']}: {t['savings']} saved "
                           f"({t['commands']} cmds)")
    finally:
        db.close()


# === Sandbox Commands ===


@cli.command()
@click.option("--purge", is_flag=True, help="Wipe all indexed content")
def sandbox(purge: bool) -> None:
    """Show sandbox knowledge base stats or purge content."""
    from gathon.sandbox import ContentStore
    store = ContentStore()
    if purge:
        before = store.stats()
        store.purge()
        click.echo(f"Purged {before['source_count']} sources, "
                    f"{before['chunk_count']} chunks, "
                    f"{before['total_bytes']} bytes")
        return
    s = store.stats()
    click.echo("Sandbox Knowledge Base")
    click.echo(f"{'=' * 40}")
    click.echo(f"Sources:  {s['source_count']}")
    click.echo(f"Chunks:   {s['chunk_count']}")
    click.echo(f"Total:    {s['total_bytes']} bytes")
    click.echo(f"DB:       {s['db_path']}")


# === Session Commands ===


@cli.command()
@click.option("--cleanup", is_flag=True, help="Delete events older than 7 days")
@click.option("--snapshot", is_flag=True, help="Show latest snapshot")
def session(cleanup: bool, snapshot: bool) -> None:
    """Show session continuity stats."""
    import os

    from gathon.session import SessionDB
    from gathon.session.hooks import _get_session_id

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
    db = SessionDB(project_dir=project_dir)
    try:
        sid = _get_session_id()
        if cleanup:
            deleted = db.cleanup_old()
            click.echo(f"Cleaned up {deleted} old records")
            return
        if snapshot:
            snap = db.get_latest_snapshot(sid)
            if snap:
                click.echo(snap)
            else:
                click.echo("No snapshot found for current session")
            return
        counts = db.get_event_counts(sid)
        total = sum(counts.values())
        click.echo(f"Session: {sid}")
        click.echo(f"Total events: {total}")
        if counts:
            click.echo("By type:")
            for event_type, count in sorted(counts.items(), key=lambda x: -x[1]):
                click.echo(f"  {event_type}: {count}")
    finally:
        db.close()


@cli.command(name="session-pre-tool")
def session_pre_tool() -> None:
    """PreToolUse hook for session continuity."""
    from gathon.session.hooks import pre_tool_use_hook
    pre_tool_use_hook()


@cli.command(name="session-post-tool")
def session_post_tool() -> None:
    """PostToolUse hook for session continuity."""
    from gathon.session.hooks import post_tool_use_hook
    post_tool_use_hook()


@cli.command(name="session-pre-compact")
def session_pre_compact() -> None:
    """PreCompact hook — build and save session snapshot."""
    from gathon.session.hooks import pre_compact_hook
    pre_compact_hook()


@cli.command(name="session-start")
def session_start() -> None:
    """SessionStart hook — restore session context."""
    from gathon.session.hooks import session_start_hook
    session_start_hook()


# === Symbol Commands ===


@cli.command()
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--force", is_flag=True, help="Force full reindex")
def symbols(path: str, force: bool) -> None:
    """Index project symbols and show stats."""
    from gathon.symbols import SymbolIndex

    root = Path(path).resolve()
    idx = SymbolIndex(project_root=str(root))
    try:
        click.echo(f"Indexing symbols: {root}")
        idx.index_project(str(root))
        s = idx.stats()
        click.echo(f"Symbols:      {s['symbol_count']}")
        click.echo(f"Files:        {s['file_count']}")
        click.echo(f"Dependencies: {s['dependency_count']}")
        click.echo(f"Languages:    {', '.join(s.get('languages', []))}")
        stale = idx.get_stale_files(str(root))
        if stale:
            click.echo(f"Stale files:  {len(stale)}")
    finally:
        idx.close()


@cli.command(name="find-symbol")
@click.argument("name")
@click.option("--exact", is_flag=True, help="Exact match only")
@click.argument("path", default=".", type=click.Path(exists=True))
def find_symbol_cmd(name: str, exact: bool, path: str) -> None:
    """Find symbol by name."""
    from gathon.symbols import SymbolIndex

    root = Path(path).resolve()
    idx = SymbolIndex(project_root=str(root))
    try:
        results = idx.find_symbol(name, exact=exact)
        if not results:
            click.echo(f"No symbols found matching '{name}'")
            return
        for s in results:
            click.echo(f"  {s.kind} {s.qualified_name}")
            click.echo(f"    {s.file_path}:{s.line_start}")
            if s.signature:
                click.echo(f"    {s.signature}")
    finally:
        idx.close()


# === Memory Commands ===


@cli.command()
@click.option("--maintain", is_flag=True, help="Run maintenance (decay, promote, dedup)")
@click.option("--search", "query", default=None, help="Search memory")
@click.option("--type", "type_filter", default=None, help="Filter by type")
def memory(maintain: bool, query: str | None, type_filter: str | None) -> None:
    """Show memory stats, search, or run maintenance."""
    from gathon.memory import MemoryDB

    db = MemoryDB()
    try:
        if maintain:
            result = db.maintain()
            click.echo(f"Decayed:  {result.get('decayed', 0)}")
            click.echo(f"Promoted: {result.get('promoted', 0)}")
            click.echo(f"Deduped:  {result.get('deduped', 0)}")
            return
        if query:
            results = db.search(query, type_filter=type_filter)
            if not results:
                click.echo("No results found.")
                return
            for r in results:
                o = r.observation
                click.echo(f"  [{o.obs_type}] {o.title} (score: {r.score:.2f})")
                if r.snippet:
                    click.echo(f"    {r.snippet[:100]}")
            return
        s = db.stats()
        click.echo("Memory Engine")
        click.echo(f"{'=' * 40}")
        click.echo(f"Total:    {s['total']}")
        click.echo(f"Archived: {s['archived']}")
        if s.get('by_type'):
            click.echo("By type:")
            for t, c in sorted(s['by_type'].items()):
                click.echo(f"  {t}: {c}")
    finally:
        db.close()


# === Prefetch Command ===


@cli.command()
@click.option("--reset", is_flag=True, help="Clear transition model")
def prefetch(reset: bool) -> None:
    """Show Markov prefetcher stats or reset."""
    from gathon.prefetch import MarkovPrefetcher

    pf = MarkovPrefetcher()
    if reset:
        pf.reset()
        click.echo("Prefetch model cleared.")
        return
    s = pf.stats()
    click.echo("Markov Prefetcher")
    click.echo(f"{'=' * 40}")
    click.echo(f"States:      {s['total_states']}")
    click.echo(f"Transitions: {s['total_transitions']}")
    click.echo(f"Sessions:    {s['session_count']}")
    if s.get('top_transitions'):
        click.echo("\nTop transitions:")
        for t in s['top_transitions'][:5]:
            click.echo(f"  {t['from']} → {t['to']} ({t['count']}x)")


@cli.command()
@click.option("--days", default=7, show_default=True, help="Days of telemetry to include")
@click.option("--repo", "repo_path", default=".", show_default=True, type=click.Path(exists=True), help="Repo root path")
@click.option("--out", "out_path", default=None, help="Output HTML path (default: ~/.gathon/dashboard.html)")
@click.option("--no-open", is_flag=True, help="Skip opening in browser")
def dashboard(days: int, repo_path: str, out_path: str | None, no_open: bool) -> None:
    """Generate unified observability dashboard."""
    import webbrowser
    from pathlib import Path

    from gathon.dashboard import generate_dashboard

    path = generate_dashboard(
        days=days,
        repo_path=Path(repo_path).resolve(),
        out_path=out_path,
    )
    click.echo(f"Dashboard → {path}")
    if not no_open:
        webbrowser.open(f"file://{path}")
