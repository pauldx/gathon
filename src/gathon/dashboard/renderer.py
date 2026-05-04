"""Standalone HTML dashboard renderer — produces a single self-contained HTML file."""

from __future__ import annotations

import json
from typing import Any

from gathon.dashboard.models import DashboardData


def _j(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


def _esc(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _fmt_tokens(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def _fmt_pct(n: float) -> str:
    return f"{n:.1f}%"


def _fmt_cost(usd: float) -> str:
    if usd >= 1.0:
        return f"${usd:.2f}"
    if usd >= 0.001:
        return f"${usd:.4f}"
    return f"${usd:.6f}"


def _stat_card(title: str, value: str, subtitle: str = "", color: str = "#4E79A7") -> str:
    return f"""
<div class="stat-card">
  <div class="stat-title">{_esc(title)}</div>
  <div class="stat-value" style="color:{color}">{_esc(value)}</div>
  {f'<div class="stat-sub">{_esc(subtitle)}</div>' if subtitle else ""}
</div>"""


def _severity_badge(severity: str) -> str:
    colors = {
        "critical": "#ef4444",
        "high": "#f97316",
        "medium": "#f59e0b",
        "low": "#22c55e",
    }
    color = colors.get(severity, "#6b7280")
    return f'<span class="badge" style="background:{color}">{_esc(severity.upper())}</span>'


def _chart_canvas(chart_id: str, height: int = 220) -> str:
    return f'<canvas id="{chart_id}" style="max-height:{height}px"></canvas>'


def _chart_bar(
    chart_id: str,
    labels: list[str],
    values: list[float],
    label: str,
    color: str = "#4E79A7",
    horizontal: bool = False,
) -> str:
    chart_type = "bar"
    index_axis = '"y"' if horizontal else '"x"'
    return f"""<script>
(function(){{
  var ctx = document.getElementById({_j(chart_id)});
  if (!ctx) return;
  new Chart(ctx, {{
    type: {_j(chart_type)},
    data: {{
      labels: {_j(labels)},
      datasets: [{{
        label: {_j(label)},
        data: {_j(values)},
        backgroundColor: {_j(color)},
        borderRadius: 3
      }}]
    }},
    options: {{
      indexAxis: {index_axis},
      responsive: true,
      plugins: {{ legend: {{ display: false }} }},
      scales: {{
        x: {{ ticks: {{ color: "#aaa" }}, grid: {{ color: "#2a2a4e" }} }},
        y: {{ ticks: {{ color: "#aaa" }}, grid: {{ color: "#2a2a4e" }} }}
      }}
    }}
  }});
}})();
</script>"""


def _chart_line(
    chart_id: str,
    labels: list[str],
    values: list[float],
    label: str,
    color: str = "#4E79A7",
) -> str:
    return f"""<script>
(function(){{
  var ctx = document.getElementById({_j(chart_id)});
  if (!ctx) return;
  new Chart(ctx, {{
    type: "line",
    data: {{
      labels: {_j(labels)},
      datasets: [{{
        label: {_j(label)},
        data: {_j(values)},
        borderColor: {_j(color)},
        backgroundColor: {_j(color + "33")},
        fill: true,
        tension: 0.3,
        pointRadius: 3
      }}]
    }},
    options: {{
      responsive: true,
      plugins: {{ legend: {{ display: false }} }},
      scales: {{
        x: {{ ticks: {{ color: "#aaa" }}, grid: {{ color: "#2a2a4e" }} }},
        y: {{ ticks: {{ color: "#aaa" }}, grid: {{ color: "#2a2a4e" }} }}
      }}
    }}
  }});
}})();
</script>"""


def _chart_doughnut(
    chart_id: str,
    labels: list[str],
    values: list[float],
    colors: list[str] | None = None,
) -> str:
    default_colors = ["#4E79A7", "#F28E2B", "#E15759", "#76B7B2", "#59A14F",
                      "#EDC948", "#B07AA1", "#FF9DA7", "#9C755F", "#BAB0AC"]
    used_colors = colors if colors else default_colors[:len(labels)]
    return f"""<script>
(function(){{
  var ctx = document.getElementById({_j(chart_id)});
  if (!ctx) return;
  new Chart(ctx, {{
    type: "doughnut",
    data: {{
      labels: {_j(labels)},
      datasets: [{{
        data: {_j(values)},
        backgroundColor: {_j(used_colors)},
        borderColor: "#0f0f1a",
        borderWidth: 2
      }}]
    }},
    options: {{
      responsive: true,
      plugins: {{
        legend: {{
          position: "right",
          labels: {{ color: "#e0e0e0", padding: 12 }}
        }}
      }}
    }}
  }});
}})();
</script>"""


def _chart_radar(
    chart_id: str,
    labels: list[str],
    values: list[float],
) -> str:
    return f"""<script>
(function(){{
  var ctx = document.getElementById({_j(chart_id)});
  if (!ctx) return;
  new Chart(ctx, {{
    type: "radar",
    data: {{
      labels: {_j(labels)},
      datasets: [{{
        label: "Score",
        data: {_j(values)},
        borderColor: "#4E79A7",
        backgroundColor: "#4E79A733",
        pointBackgroundColor: "#4E79A7",
        pointRadius: 4
      }}]
    }},
    options: {{
      responsive: true,
      scales: {{
        r: {{
          min: 0, max: 100,
          ticks: {{ color: "#aaa", stepSize: 20, backdropColor: "transparent" }},
          grid: {{ color: "#2a2a4e" }},
          pointLabels: {{ color: "#e0e0e0", font: {{ size: 11 }} }}
        }}
      }},
      plugins: {{ legend: {{ display: false }} }}
    }}
  }});
}})();
</script>"""


def _render_css() -> str:
    return """
:root {
  --bg: #0f0f1a;
  --sidebar: #1a1a2e;
  --border: #2a2a4e;
  --text: #e0e0e0;
  --text-dim: #aaa;
  --accent: #4E79A7;
  --success: #22c55e;
  --warning: #f59e0b;
  --danger: #ef4444;
  --card: #1e1e30;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: var(--bg); color: var(--text); font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; display: flex; min-height: 100vh; }
.sidebar { width: 200px; background: var(--sidebar); border-right: 1px solid var(--border); padding: 16px 0; position: fixed; top: 0; left: 0; height: 100vh; overflow-y: auto; z-index: 10; }
.sidebar-title { padding: 0 16px 16px; font-size: 14px; font-weight: 700; color: var(--accent); letter-spacing: 0.5px; }
.nav-item { display: block; padding: 10px 16px; color: var(--text-dim); cursor: pointer; font-size: 13px; border-left: 3px solid transparent; transition: all 0.15s; }
.nav-item:hover { color: var(--text); background: rgba(78,121,167,0.1); }
.nav-item.active { color: var(--accent); border-left-color: var(--accent); background: rgba(78,121,167,0.1); }
.main { margin-left: 200px; flex: 1; padding: 24px; }
.tab-section { display: none; }
.tab-section.active { display: block; }
h2 { font-size: 20px; font-weight: 600; margin-bottom: 16px; }
h3 { font-size: 15px; font-weight: 600; margin-bottom: 12px; color: var(--text-dim); }
.stat-row { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 20px; }
.stat-card { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 16px; min-width: 140px; flex: 1; }
.stat-title { font-size: 11px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px; }
.stat-value { font-size: 22px; font-weight: 700; }
.stat-sub { font-size: 11px; color: var(--text-dim); margin-top: 4px; }
.card { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 16px; margin-bottom: 16px; }
.chart-wrap { position: relative; }
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.grid-3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { padding: 8px 12px; text-align: left; border-bottom: 1px solid var(--border); }
th { color: var(--text-dim); font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; }
td { color: var(--text); }
.badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 10px; font-weight: 700; color: #fff; }
.grade { font-size: 64px; font-weight: 900; line-height: 1; }
.grade-S { color: #22c55e; }
.grade-A { color: #4E79A7; }
.grade-B { color: #06b6d4; }
.grade-C { color: #f59e0b; }
.grade-D { color: #f97316; }
.grade-F { color: #ef4444; }
.pattern-card { background: var(--card); border: 1px solid var(--border); border-radius: 6px; padding: 12px 14px; margin-bottom: 8px; }
.pattern-good { border-left: 3px solid #22c55e; }
.pattern-bad { border-left: 3px solid #ef4444; }
.pattern-label { font-weight: 600; font-size: 13px; margin-bottom: 4px; }
.pattern-detail { font-size: 12px; color: var(--text-dim); }
.finding-card { background: var(--card); border: 1px solid var(--border); border-radius: 6px; padding: 14px; margin-bottom: 10px; }
.finding-header { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.finding-type { font-weight: 600; font-size: 13px; }
.finding-desc { font-size: 13px; color: var(--text-dim); margin-bottom: 6px; }
.finding-rec { font-size: 12px; color: #4E79A7; font-style: italic; }
.empty-msg { color: var(--text-dim); font-size: 13px; font-style: italic; padding: 24px 0; text-align: center; }
.meta { font-size: 11px; color: var(--text-dim); margin-bottom: 20px; }
"""


def _render_nav(active_tab: str = "overview") -> str:
    tabs = [
        ("overview", "Overview"),
        ("ctp", "CLI Token Parse"),
        ("codegraph", "Code Graph"),
        ("multimodal", "Multimodal"),
        ("memory", "Memory"),
        ("quality", "Quality"),
        ("waste", "Waste"),
        ("coach", "Coach"),
    ]
    items = "\n".join(
        f'<div class="nav-item{" active" if t[0] == active_tab else ""}" data-tab="{t[0]}">{t[1]}</div>'
        for t in tabs
    )
    return f"""
<div class="sidebar">
  <div class="sidebar-title">gathon</div>
  {items}
</div>"""


def _render_overview(data: DashboardData) -> str:
    ov = data.overview
    trend_dates = [e["date"] for e in ov.trend]
    trend_vals = [e["savings"] for e in ov.trend]

    modules = ["CLI Token Parse", "Code Graph", "Memory Est."]
    mod_vals = [ov.ctp_savings, ov.graph_savings, ov.memory_savings]
    mod_vals_clean = [max(0, v) for v in mod_vals]

    return f"""
<div class="tab-section active" id="tab-overview">
  <h2>Overview</h2>
  <div class="meta">Generated {_esc(data.generated_at)} · Last {data.days} days · {_esc(data.repo_path)}</div>
  <div class="stat-row">
    {_stat_card("Total Tokens Saved", _fmt_tokens(ov.total_savings_tokens), "across all modules", "#22c55e")}
    {_stat_card("Est. Cost Saved", _fmt_cost(ov.estimated_cost_usd), "at Sonnet input rates", "#f59e0b")}
    {_stat_card("CTP Savings", _fmt_tokens(ov.ctp_savings), "CLI filter compression")}
    {_stat_card("Graph Savings", _fmt_tokens(ov.graph_savings), "MCP tool compression")}
    {_stat_card("Memory Reuse", _fmt_tokens(ov.memory_savings), "estimated from access counts")}
    {_stat_card("Session Events", str(ov.session_event_count), "total logged events")}
  </div>
  <div class="grid-2">
    <div class="card">
      <h3>Savings by Module</h3>
      <div class="chart-wrap">{_chart_canvas("chart-overview-donut", 240)}</div>
      {_chart_doughnut("chart-overview-donut", modules, mod_vals_clean)}
    </div>
    <div class="card">
      <h3>Savings Trend ({data.days}d)</h3>
      <div class="chart-wrap">{_chart_canvas("chart-overview-trend", 240)}</div>
      {_chart_line("chart-overview-trend", trend_dates, trend_vals, "Tokens Saved", "#4E79A7")}
    </div>
  </div>
</div>"""


def _render_ctp(data: DashboardData) -> str:
    ctp = data.ctp
    filter_labels = [f["filter"] for f in ctp.by_filter[:15]]
    filter_vals = [f.get("savings", 0) for f in ctp.by_filter[:15]]
    trend_dates = [e["date"] for e in ctp.trend]
    trend_savings = [e.get("savings", 0) for e in ctp.trend]

    table_rows = "".join(
        f"<tr><td>{_esc(f['filter'])}</td><td>{f['count']}</td>"
        f"<td>{_fmt_tokens(f.get('savings', 0))}</td>"
        f"<td>{_fmt_pct(f.get('avg_pct', 0))}</td>"
        f"<td>{f.get('avg_ms', 0):.0f}ms</td></tr>"
        for f in ctp.by_filter
    ) or '<tr><td colspan="5" class="empty-msg">No CTP data yet. Run `gathon ctp-init`.</td></tr>'

    return f"""
<div class="tab-section" id="tab-ctp">
  <h2>CLI Token Parse</h2>
  <div class="stat-row">
    {_stat_card("Commands Filtered", str(ctp.total_commands))}
    {_stat_card("Tokens Saved", _fmt_tokens(ctp.total_savings), color="#22c55e")}
    {_stat_card("Avg Savings", _fmt_pct(ctp.avg_savings_pct), "per command")}
  </div>
  <div class="grid-2">
    <div class="card">
      <h3>Savings by Filter (top 15)</h3>
      <div class="chart-wrap">{_chart_canvas("chart-ctp-filter", 280)}</div>
      {_chart_bar("chart-ctp-filter", filter_labels, filter_vals, "Tokens Saved", "#4E79A7", horizontal=True)}
    </div>
    <div class="card">
      <h3>Daily Trend</h3>
      <div class="chart-wrap">{_chart_canvas("chart-ctp-trend", 280)}</div>
      {_chart_line("chart-ctp-trend", trend_dates, trend_savings, "Tokens Saved", "#06b6d4")}
    </div>
  </div>
  <div class="card">
    <h3>Filter Performance</h3>
    <table>
      <thead><tr><th>Filter</th><th>Runs</th><th>Tokens Saved</th><th>Avg %</th><th>Avg Time</th></tr></thead>
      <tbody>{table_rows}</tbody>
    </table>
  </div>
</div>"""


def _render_code_graph(data: DashboardData) -> str:
    cg = data.code_graph
    summary = cg.compression_summary
    unified = cg.unified_stats

    tool_labels = [t["tool"] for t in cg.by_tool[:12]]
    tool_vals = [t.get("savings_tokens", 0) for t in cg.by_tool[:12]]

    trend_dates = [e["date"] for e in cg.trend]
    trend_vals = [e.get("savings_tokens", 0) for e in cg.trend]

    pipeline_counts = cg.pipeline_run_summary.get("counts", {})
    pl_labels = list(pipeline_counts.keys())[:10]
    pl_vals = [pipeline_counts[k] for k in pl_labels]

    disc = cg.disclosure_stats
    index_q = disc.get("index_queries", 0)
    full_q = disc.get("full_queries", 0)

    total_nodes = unified.get("total_nodes", 0)
    total_edges = unified.get("total_edges", 0)

    return f"""
<div class="tab-section" id="tab-codegraph">
  <h2>Code Graph</h2>
  <div class="stat-row">
    {_stat_card("Nodes", str(total_nodes))}
    {_stat_card("Edges", str(total_edges))}
    {_stat_card("Compress Events", str(summary.get("total_events", 0)))}
    {_stat_card("Tokens Saved", _fmt_tokens(summary.get("total_savings_tokens", 0)), color="#22c55e")}
    {_stat_card("Avg Savings", _fmt_pct(summary.get("avg_savings_pct", 0.0)))}
    {_stat_card("Index/Full", f"{index_q}/{full_q}", "query depth split")}
  </div>
  <div class="grid-2">
    <div class="card">
      <h3>Compression by MCP Tool (top 12)</h3>
      <div class="chart-wrap">{_chart_canvas("chart-cg-tool", 280)}</div>
      {_chart_bar("chart-cg-tool", tool_labels, tool_vals, "Tokens Saved", "#4E79A7", horizontal=True)}
    </div>
    <div class="card">
      <h3>Compression Trend ({data.days}d)</h3>
      <div class="chart-wrap">{_chart_canvas("chart-cg-trend", 280)}</div>
      {_chart_line("chart-cg-trend", trend_dates, trend_vals, "Tokens Saved", "#22c55e")}
    </div>
  </div>
  <div class="grid-2">
    <div class="card">
      <h3>Pipeline Build Runs</h3>
      <div class="chart-wrap">{_chart_canvas("chart-cg-pipeline", 200)}</div>
      {_chart_bar("chart-cg-pipeline", pl_labels, pl_vals, "Runs", "#59A14F")}
    </div>
    <div class="card">
      <h3>Query Depth (Index vs Full)</h3>
      <div class="chart-wrap">{_chart_canvas("chart-cg-disc", 200)}</div>
      {_chart_doughnut("chart-cg-disc", ["Index", "Full"], [index_q, full_q], ["#4E79A7", "#F28E2B"])}
    </div>
  </div>
</div>"""


def _render_multimodal(data: DashboardData) -> str:
    mm = data.multimodal
    pipe_labels = list(mm.nodes_by_pipeline.keys())
    pipe_vals = [mm.nodes_by_pipeline[k] for k in pipe_labels]

    run_labels = [k for k, v in mm.pipeline_run_counts.items() if v > 0]
    run_vals = [mm.pipeline_run_counts[k] for k in run_labels]

    tool_labels = [t["tool"] for t in mm.compression_by_pipeline[:8]]
    tool_vals = [t.get("savings_tokens", 0) for t in mm.compression_by_pipeline[:8]]

    return f"""
<div class="tab-section" id="tab-multimodal">
  <h2>Multimodal</h2>
  <div class="stat-row">
    {_stat_card("Multimodal Nodes", str(mm.total_multimodal_nodes))}
    {_stat_card("Pipelines Active", str(len([v for v in mm.nodes_by_pipeline.values() if v > 0])))}
  </div>
  <div class="grid-2">
    <div class="card">
      <h3>Nodes by Pipeline</h3>
      <div class="chart-wrap">{_chart_canvas("chart-mm-nodes", 250)}</div>
      {_chart_bar("chart-mm-nodes", pipe_labels, pipe_vals, "Nodes", "#8E44AD")}
    </div>
    <div class="card">
      <h3>Pipeline Build Runs</h3>
      <div class="chart-wrap">{_chart_canvas("chart-mm-runs", 250)}</div>
      {_chart_bar("chart-mm-runs", run_labels, run_vals, "Runs", "#E67E22")}
    </div>
  </div>
  {"" if not tool_labels else f'''
  <div class="card">
    <h3>Compression Savings by Ingest Tool</h3>
    <div class="chart-wrap">{_chart_canvas("chart-mm-savings", 200)}</div>
    {_chart_bar("chart-mm-savings", tool_labels, tool_vals, "Tokens Saved", "#9b59b6", horizontal=True)}
  </div>'''}
  {"" if mm.total_multimodal_nodes > 0 else '<div class="empty-msg">No multimodal content ingested yet. Use `gathon build` or `ingest_url` MCP tool.</div>'}
</div>"""


def _render_memory(data: DashboardData) -> str:
    mem = data.memory
    type_labels = list(mem.by_type.keys())
    type_vals = [mem.by_type[k] for k in type_labels]
    roi_labels = [b["range"] for b in mem.roi_distribution]
    roi_vals = [b["count"] for b in mem.roi_distribution]

    return f"""
<div class="tab-section" id="tab-memory">
  <h2>Memory</h2>
  <div class="stat-row">
    {_stat_card("Observations", str(mem.total))}
    {_stat_card("Archived", str(mem.archived), f"{mem.archive_rate_pct:.1f}% archive rate")}
    {_stat_card("Avg Importance", f"{mem.avg_importance:.2f}", "0=low, 1=high")}
    {_stat_card("Est. Reuse Savings", _fmt_tokens(mem.estimated_reuse_savings), "from access counts", "#22c55e")}
  </div>
  <div class="grid-2">
    <div class="card">
      <h3>Observations by Type</h3>
      <div class="chart-wrap">{_chart_canvas("chart-mem-type", 250)}</div>
      {_chart_doughnut("chart-mem-type", type_labels, type_vals) if type_labels else '<div class="empty-msg">No observations yet.</div>'}
    </div>
    <div class="card">
      <h3>Importance Distribution</h3>
      <div class="chart-wrap">{_chart_canvas("chart-mem-roi", 250)}</div>
      {_chart_bar("chart-mem-roi", roi_labels, roi_vals, "Observations", "#59A14F")}
    </div>
  </div>
</div>"""


def _render_quality(data: DashboardData) -> str:
    q = data.quality
    signal_labels = [s.name for s in q.signals]
    signal_vals = [round(s.score, 1) for s in q.signals]

    signal_rows = "".join(
        f"<tr><td>{_esc(s.name)}</td>"
        f"<td>{_fmt_pct(s.weight * 100)}</td>"
        f"<td>{s.score:.0f}/100</td>"
        f"<td style='color:var(--text-dim);font-size:12px'>{_esc(s.description)}</td></tr>"
        for s in q.signals
    )

    recs = "".join(
        f'<li style="margin-bottom:6px;font-size:13px">{_esc(r)}</li>'
        for r in q.recommendations
    )

    return f"""
<div class="tab-section" id="tab-quality">
  <h2>Quality Score</h2>
  <div style="display:flex;align-items:center;gap:24px;margin-bottom:20px">
    <div>
      <div class="grade grade-{_esc(q.grade)}">{_esc(q.grade)}</div>
      <div style="font-size:14px;margin-top:6px;color:var(--text-dim)">{_esc(q.band)} &mdash; {q.score:.1f}/100</div>
    </div>
    <div style="flex:1;max-width:340px">
      {_chart_canvas("chart-quality-radar", 280)}
      {_chart_radar("chart-quality-radar", signal_labels, signal_vals)}
    </div>
  </div>
  <div class="card">
    <h3>Signal Breakdown</h3>
    <table>
      <thead><tr><th>Signal</th><th>Weight</th><th>Score</th><th>Detail</th></tr></thead>
      <tbody>{signal_rows}</tbody>
    </table>
  </div>
  {"" if not recs else f'<div class="card"><h3>Recommendations</h3><ul style="padding-left:18px">{recs}</ul></div>'}
</div>"""


def _render_waste(data: DashboardData) -> str:
    wt = data.waste
    counts = wt.severity_counts
    sev_labels = ["critical", "high", "medium", "low"]
    sev_vals = [counts.get(s, 0) for s in sev_labels]
    sev_colors = ["#ef4444", "#f97316", "#f59e0b", "#22c55e"]

    finding_cards = "".join(
        f"""<div class="finding-card">
  <div class="finding-header">
    {_severity_badge(f.severity)}
    <span class="finding-type">{_esc(f.waste_type.replace("_", " ").title())}</span>
  </div>
  <div class="finding-desc">{_esc(f.description)}</div>
  <div class="finding-rec">&#x2192; {_esc(f.recommendation)}</div>
</div>"""
        for f in wt.findings
    ) or '<div class="empty-msg">No waste patterns detected.</div>'

    return f"""
<div class="tab-section" id="tab-waste">
  <h2>Waste Patterns</h2>
  <div class="grid-2">
    <div class="stat-row" style="margin-bottom:0">
      {_stat_card("Total Findings", str(len(wt.findings)))}
      {_stat_card("Critical", str(counts.get("critical", 0)), color="#ef4444")}
      {_stat_card("Medium", str(counts.get("medium", 0)), color="#f59e0b")}
      {_stat_card("Low", str(counts.get("low", 0)), color="#22c55e")}
    </div>
    <div class="card">
      <h3>Severity Breakdown</h3>
      <div class="chart-wrap">{_chart_canvas("chart-waste-sev", 160)}</div>
      {_chart_doughnut("chart-waste-sev", sev_labels, sev_vals, sev_colors)}
    </div>
  </div>
  <div style="margin-top:16px">{finding_cards}</div>
</div>"""


def _render_coach(data: DashboardData) -> str:
    coach = data.coach
    score = coach.health_score
    grade_color = {
        "S": "#22c55e", "A": "#4E79A7", "B": "#06b6d4",
        "C": "#f59e0b", "D": "#f97316", "F": "#ef4444",
    }.get(coach.grade, "#aaa")

    good_cards = "".join(
        f'<div class="pattern-card pattern-good"><div class="pattern-label">{_esc(p.label)}</div><div class="pattern-detail">{_esc(p.detail)}</div></div>'
        for p in coach.patterns_good
    ) or "<div class='empty-msg'>No strengths detected yet.</div>"

    bad_cards = "".join(
        f'<div class="pattern-card pattern-bad"><div class="pattern-label">{_esc(p.label)}</div><div class="pattern-detail">{_esc(p.detail)}</div></div>'
        for p in coach.patterns_bad
    ) or "<div class='empty-msg'>No issues detected.</div>"

    snap = coach.snapshot
    gauge_pct = score / 100
    gauge_angle = gauge_pct * 180

    return f"""
<div class="tab-section" id="tab-coach">
  <h2>Coach</h2>
  <div style="display:flex;align-items:center;gap:24px;margin-bottom:20px">
    <div style="text-align:center">
      <canvas id="chart-coach-gauge" width="200" height="110"></canvas>
      <script>
(function(){{
  var ctx = document.getElementById("chart-coach-gauge");
  if (!ctx) return;
  new Chart(ctx, {{
    type: "doughnut",
    data: {{
      datasets: [{{
        data: [{score}, {100 - score}],
        backgroundColor: [{_j(grade_color)}, "#1e1e30"],
        borderWidth: 0,
        circumference: 180,
        rotation: 270
      }}]
    }},
    options: {{
      responsive: false,
      cutout: "75%",
      plugins: {{ legend: {{ display: false }}, tooltip: {{ enabled: false }} }}
    }}
  }});
}})();
      </script>
      <div style="margin-top:-30px;font-size:28px;font-weight:900;color:{grade_color}">{score}</div>
      <div style="font-size:12px;color:var(--text-dim)">Health Score &mdash; Grade {_esc(coach.grade)}</div>
    </div>
    <div class="stat-row" style="flex:1">
      {_stat_card("CTP Savings", _fmt_tokens(snap.get("total_ctp_savings", 0)))}
      {_stat_card("Graph Savings", _fmt_tokens(snap.get("total_graph_savings", 0)))}
      {_stat_card("Memory Obs.", str(snap.get("memory_observations", 0)))}
      {_stat_card("Active Modules", str(snap.get("active_modules", 0)), "/ 4 total")}
    </div>
  </div>
  <div class="grid-2">
    <div>
      <h3 style="margin-bottom:10px;color:#22c55e">&#x2714; Working Well</h3>
      {good_cards}
    </div>
    <div>
      <h3 style="margin-bottom:10px;color:#ef4444">&#x26A0; Issues</h3>
      {bad_cards}
    </div>
  </div>
</div>"""


def _render_tab_js() -> str:
    return """
<script>
(function() {
  var items = document.querySelectorAll(".nav-item");
  var sections = document.querySelectorAll(".tab-section");
  items.forEach(function(el) {
    el.addEventListener("click", function() {
      var tab = el.getAttribute("data-tab");
      items.forEach(function(i) { i.classList.remove("active"); });
      sections.forEach(function(s) { s.classList.remove("active"); });
      el.classList.add("active");
      var target = document.getElementById("tab-" + tab);
      if (target) target.classList.add("active");
    });
  });
})();
</script>"""


def render(data: DashboardData) -> str:
    css = _render_css()
    nav = _render_nav()
    overview = _render_overview(data)
    ctp = _render_ctp(data)
    code_graph = _render_code_graph(data)
    multimodal = _render_multimodal(data)
    memory = _render_memory(data)
    quality = _render_quality(data)
    waste = _render_waste(data)
    coach = _render_coach(data)
    tab_js = _render_tab_js()

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Gathon Dashboard</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
  <style>{css}</style>
</head>
<body>
  {nav}
  <div class="main">
    {overview}
    {ctp}
    {code_graph}
    {multimodal}
    {memory}
    {quality}
    {waste}
    {coach}
  </div>
  {tab_js}
</body>
</html>"""
