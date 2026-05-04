# Gathon — Unified Adaptive Knowledge Graph Engine

**GATHON** (Bengali: "weaving") is a production-grade token-optimization platform that builds a unified knowledge graph from code, documentation, APIs, and media, then exposes it to AI agents via **58 MCP tools** with sophisticated context compression, packing, and prefetching mechanisms.

---

## Core Value Proposition

**Reduce LLM API costs by 70–90%** across every layer of the AI agent stack — without sacrificing code understanding or developer experience.

| Module | What it solves | Savings |
|--------|---------------|---------|
| `code_graph/` | Surgical structural context via queryable call graph | **90%+** per query |
| `multimodal_graph/` | Structured extraction of docs, PDFs, APIs, media | **~99%** vs raw injection |
| `memory/` | Cross-session typed observations replace repeat tool chains | **3–10 tool calls** → 1 |
| `cli_token_parse/` | 27 Bash output filters applied before model sees stdout | **40–80%** on CLI output |
| `dashboard/` | Unified telemetry across all 4 DBs → actionable grade S–F | — |

### 🕸️ Code Graph
Tree-sitter parses 20+ languages into a queryable SQLite graph (functions · classes · imports · calls). Agents get **2–5K tokens of targeted context** instead of 50–200K raw file content. Louvain communities, DFS execution flows, FTS5 search, and risk-scored change impact — all queryable via 58 MCP tools with progressive `index`/`full` disclosure.

### 🌐 Multimodal Graph
Ingests every non-code artifact — Markdown, PDF, Office, OpenAPI, YAML, images (Claude vision), video (Whisper), URLs — as structured graph nodes. A 50-page PDF → ≤51 nodes with section previews instead of ~25K injected tokens per query. Node labels compressed at ingestion; code + docs + APIs traversable in a single graph query.

### 🧠 Cross-Session Memory
BM25-searchable typed observation store (guardrails · decisions · bugfixes · conventions). `memory_search()` replaces 3–10 tool-call chains that would re-discover the same facts each session. ROI scoring (`access_count × importance × recency`) surfaces highest-value memories first; contradiction detection prevents stale observations from misleading the model.

### ⚡ CLI Token Parse
PreToolUse hook intercepts every Bash call and routes stdout through 27 command-specific noise filters before it reaches the model. `pytest` 800 → 120 tokens (85%). `git diff` strips context lines and whitespace. Filters ranked by historical `avg_savings_pct`; parallel evaluation via `ThreadPoolExecutor`; SHA-256 TTL cache for repeated commands.

### 📊 Observability Dashboard
`gathon dashboard` generates a standalone dark-themed HTML file from 4 telemetry databases (`cli_parser.db` · `graph.db` · `memory.db` · `sessions/*.db`). 8 tabs: savings overview, per-filter analytics, graph compression, multimodal ingestion, memory ROI, 7-signal quality radar (grade S–F), waste detectors, and health coach.

---

## Table of Contents

1. [Installation](#installation)
2. [Integrate Into Any Repo](#integrate-into-any-repo)
3. [CLI Commands](#cli-commands)
4. [Claude Code Integration](#claude-code-integration)
5. [Optimization Details](#optimization-details)
6. [Observability Dashboard](#observability-dashboard)
7. [Performance Metrics](#performance-metrics)
8. [Architecture Diagrams](#architecture-diagrams)
9. [Troubleshooting](#troubleshooting)

---

## Installation

**Requirements**: Python 3.11+, `pip`

```bash
# Clone and install
git clone https://github.com/pauldx/gathon.git
cd gathon
pip install -e .

# Verify
gathon --version
```

**Optional dependencies** (enable additional pipelines):

```bash
pip install -e ".[pdf]"      # PDF ingestion (pypdf)
pip install -e ".[office]"   # Office docs (python-docx, openpyxl)
pip install -e ".[vision]"   # Image/video (requires Claude API key)
pip install -e ".[all]"      # Everything
```

---

## Integrate Into Any Repo

Three commands to get full token optimization running against any codebase:

```bash
# 1. Build the knowledge graph (run once, then incrementally)
gathon build /path/to/your/repo --full --compress full

# 2. Start the MCP server for Claude Code
gathon serve /path/to/your/repo --compress ultra

# 3. View token savings dashboard
gathon dashboard --repo /path/to/your/repo --days 30
```

**First-time setup for a repo**:

```bash
# Full build — parses all code, docs, configs, APIs
gathon build /your/repo --full --compress full
# Output: ✅ 4,231 nodes · 18,876 edges built → .gathon/graph.db

# Subsequent runs — only re-parses changed files
gathon build /your/repo --compress full
# Output: ✅ Updated 15 nodes (43 files unchanged)
```

**Claude Code MCP config** — add to `.claude/settings.json` in your repo:

```json
{
  "mcpServers": {
    "gathon": {
      "command": "gathon",
      "args": ["serve", "/path/to/your/repo", "--compress", "ultra"]
    }
  }
}
```

**Activate CLI Token Parse** — add to `.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "gathon ctp-hook"
          }
        ]
      }
    ]
  }
}
```

Once configured, Claude Code automatically gets 58 MCP tools for graph queries, CLI output is filtered before the model sees it, and every interaction is logged for the observability dashboard.

---

## CLI Commands

### `gathon build`

Build or incrementally update the knowledge graph for a repository.

```bash
gathon build /path/to/repo [OPTIONS]

Options:
  --full              Full rebuild (default: incremental if .gathon/graph.db exists)
  --base GIT_REF      Git reference for incremental diff (default: HEAD~1)
  --compress LEVEL    Compression for stored nodes: off|lite|full|ultra (default: off)
```

```bash
# First-time full build
gathon build /your/repo --full --compress full

# Incremental (only re-parses changed files since HEAD~1)
gathon build /your/repo

# Incremental from a specific base commit
gathon build /your/repo --base origin/main
```

---

### `gathon serve`

Start the MCP server exposing 58 tools to Claude Code.

```bash
gathon serve /path/to/repo [OPTIONS]

Options:
  --transport TRANSPORT  MCP transport: stdio (default)
  --compress LEVEL       Response compression: off|lite|full|ultra
```

```bash
# Standard (recommended for most use)
gathon serve /your/repo --compress full

# Maximum token savings (production/cost-sensitive)
gathon serve /your/repo --compress ultra

# No compression (debugging/development)
gathon serve /your/repo --compress off
```

**Environment variables**:
```bash
export GATHON_COMPRESS=ultra    # Default compression level
export GATHON_DB_PATH=/path     # Override .gathon/graph.db location
export GATHON_DEBUG=1           # Enable debug logging
```

---

### `gathon dashboard`

Generate a unified observability dashboard from all telemetry sources.

```bash
gathon dashboard [OPTIONS]

Options:
  --days N     Days of telemetry to include (default: 7)
  --repo PATH  Repository root (default: current directory)
  --out PATH   Output HTML file (default: ~/.gathon/dashboard.html)
  --no-open    Skip opening in browser
```

```bash
# Last 7 days, opens browser automatically
gathon dashboard

# Last 30 days for a specific repo
gathon dashboard --days 30 --repo /your/repo

# CI / scripted — no browser open
gathon dashboard --days 14 --no-open --out /tmp/report.html
```

Output: standalone `~/.gathon/dashboard.html` — dark-themed, 8 tabs, embedded Chart.js. No server required.

---

### `gathon status`

Show graph statistics for a repository.

```bash
gathon status /path/to/repo
```

```
Graph Stats:
  Nodes: 15,234 (1,200 functions, 340 classes, 8,900 docs)
  Edges: 42,891
  Files: 1,247
  Storage: 24.3 MB
  Compressed: Yes (full)
  Last Updated: 2 hours ago
```

---

### `gathon compression`

Analyze compression impact on stored graph.

```bash
gathon compression /path/to/repo --analyze

Compression Impact:
  Original size:         128 MB
  Compressed (lite):     115 MB (10% reduction)
  Compressed (full):      96 MB (25% reduction)
  Compressed (ultra):     71 MB (44% reduction)
```

```bash
# View compression telemetry (last 30 days)
gathon compression --days 30
```

---

### `gathon ctp-gain`

Show CLI Token Parse savings by filter.

```bash
gathon ctp-gain --days 30
```

---

## Claude Code Integration

Once `gathon serve` is running and configured in `.claude/settings.json`, Claude has access to 58 MCP tools. Key tools by use case:

### Code exploration

```
query_graph(target="AuthManager.login", pattern="callers_of", detail_level="index")
→ Returns callers list with _token_meta showing 156 tokens used

get_node_detail(name="auth_service.py::AuthManager.login", detail_level="full")
→ Full function: signature, docstring, dependencies, tests
```

### Context-efficient analysis

```
get_minimal_context(target="AuthManager.login", budget_tokens=5000, query="find all login callers")
→ Greedy-packed top-N relevant nodes within token budget

get_architecture_overview(root="api/", depth=3)
→ Compressed dependency DAG (~45 tokens vs ~450 raw)
```

### Code review

```
detect_breaking_changes(base="origin/main")
→ Signature changes, parameter additions, impact analysis

analyze_god_nodes()
→ Overly complex functions ranked by cyclomatic complexity

safe_refactor_suggestions(target="AuthManager")
→ Extract-method suggestions with breaking-change risk
```

### Memory (cross-session)

```
memory_save(title="Auth architecture", content="JWT tokens stored in Redis...", importance=0.8)
→ Saves to ~/.gathon/memory/memory.db

memory_search(query="authentication approach")
→ Top-5 observations (replaces 3–10 repeated tool calls)
```

The `_token_meta` field on every response tells Claude whether `detail_level="full"` is worth the additional token cost:

```json
"_token_meta": {
  "estimated_tokens": 156,
  "result_count": 5,
  "avg_tokens_per_result": 31
}
```

---

## Optimization Details

### Token savings by mechanism

| Mechanism | Savings | When active |
|-----------|---------|-------------|
| **CLI Token Parse** | 40–80% | Any Bash command via PreToolUse hook |
| **Text Compression** | 10–45% | All MCP tool responses (`--compress` flag) |
| **Context Packing** | 70–90% | `get_minimal_context` calls |
| **Progressive Disclosure** | 40–80% | Any query with `detail_level="index"` |
| **Cross-Session Memory** | variable | `memory_search` replaces tool-call chains |
| **Predictive Prefetch** | 5–10% + latency | Follow-up tool calls (Markov chain) |
| **Incremental Build** | 85–97% | `gathon build` after first full run |

### Compression levels

| Level | Reduction | Strategy |
|-------|-----------|----------|
| `lite` | 10–15% | Remove articles, fillers, hedging |
| `full` | 20–30% | Lite + phrase replacements + pleasantries |
| `ultra` | 30–45% | Full + abbreviations (DB, auth, config) |

Code, URLs, and identifiers are **never modified** at any compression level.

---

## Observability Dashboard

```bash
gathon dashboard --days 30
```

### Dashboard Tabs

| Tab | Data Source | What it shows |
|-----|-------------|---------------|
| **Overview** | All 4 DBs | Total tokens saved, cost estimate, savings donut, trend line |
| **CLI Token Parse** | `~/.gathon/cli_parser.db` | Per-filter savings bar chart, daily trend, top commands |
| **Code Graph** | `.gathon/graph.db` | Per-MCP-tool compression, pipeline build times, index vs full split |
| **Multimodal** | `.gathon/graph.db` nodes | Nodes by pipeline, per-pipeline ingestion compression |
| **Memory** | `~/.gathon/memory/memory.db` | Observation type distribution, importance score distribution |
| **Quality** | Computed across all | 7-signal radar chart, letter grade S/A/B/C/D/F |
| **Waste** | Cross-source analysis | 7 waste pattern detectors with severity cards |
| **Coach** | Cross-source analysis | Health score 0–100, good/bad pattern cards, module adoption |

### Telemetry databases

| Database | Location | Contents |
|----------|----------|---------|
| `cli_parser.db` | `~/.gathon/cli_parser.db` | CLI filter runs: filter_name, before/after tokens, savings_pct |
| `graph.db` | `<repo>/.gathon/graph.db` | MCP tool compression events, pipeline build runs |
| `memory.db` | `~/.gathon/memory/memory.db` | Observations, importance scores, access counts |
| `sessions/*.db` | `~/.gathon/sessions/` | Session event logs per project |

---

## Performance Metrics

### 10K-line Python repository

#### Code Review (5 queries)

| Metric | Without Gathon | With Gathon | Savings |
|--------|---------------|-------------|---------|
| Input tokens/query | 45,000 | 3,500 | **92%** |
| Queries/dollar | 2.2 | 28.6 | **13x** |
| Total cost/review | $0.28 | $0.02 | **93%** |
| Latency/query | 8–12s | 0.5–2s | **6–20x faster** |

#### Architecture Analysis (10 queries, large repo)

| Metric | Without Gathon | With Gathon | Savings |
|--------|---------------|-------------|---------|
| Avg tokens/query | 180,000 | 8,000 | **96%** |
| Total cost/analysis | $2.80 | $0.12 | **96%** |

#### Incremental Builds

| Scenario | Full Extraction | Incremental + Hash | Savings |
|----------|----------------|-------------------|---------|
| 1 file changed (10K files total) | 120s | 3s | **97%** |
| 5 files changed (50K functions) | 180s | 8s | **96%** |
| 10% of files changed | 120s | 15s | **87%** |

---

## Architecture Diagrams

Rendered SVGs in [`docs/`](docs/). Mermaid source (`.mmd`) co-located for editing.

- [System Architecture](docs/arch-overview.svg) — 6-layer stack: AI agent → MCP server → token optimization → unified graph → multi-pipeline extraction → observability
- [Token Optimization Pipeline](docs/token-optimization.svg) — all 6 mechanisms side by side: CTP, compression, packing, memory, prefetch, progressive disclosure
- [Knowledge Graph Data Flow](docs/data-flow.svg) — sequence: build (files → parsers → SQLite), serve (agent query → BFS → compress → token-meta), memory (save + cross-session recall)
- [Dashboard Architecture](docs/dashboard-arch.svg) — 4 telemetry DBs → logic layer (quality, waste, coach) → 8-tab standalone HTML

---

## Troubleshooting

### "No graph.db found"

```bash
gathon build /path/to/repo --full
```

### Slow incremental updates

```bash
# Specify exact base instead of HEAD~1
gathon build /path/to/repo --base origin/main
```

### Ultra compression reduces clarity

Switch to `full` for standard use; use `ultra` only for batch/cost-critical scenarios:

```bash
gathon serve /your/repo --compress full
```

### Dashboard shows no data

Ensure compression and CTP hooks are active — telemetry only accumulates when optimization layers run:

```bash
gathon build /your/repo --compress full   # populates graph.db
gathon ctp-gain                           # check CTP is firing
```

---

## Contributing

Contributions welcome — language support (Tree-sitter parsers), compression patterns, new MCP tools, and quality signal improvements.

---

## License

MIT License — free to use, modify, and distribute with attribution. See [LICENSE](LICENSE).

---

## Contact

**Author**: Debashis Paul  
**Email**: paul.debashis@gmail.com  
**Repository**: https://github.com/pauldx/gathon
