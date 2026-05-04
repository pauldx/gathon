---
name: code-optmz-graphify
description: "Fetch, build, install, and optimize knowledge graphs from repositories. Use when user wants to create AST-based graphs, manage graph storage, or apply optimization strategies."
trigger: /code-optmz-graphify
---

# /code-optmz-graphify

Unified skill for fetching, building, installing, and optimizing knowledge graphs from code repositories and corpora. Bridges `graphify` (document-centric) and `gathon` (code-centric) graph systems.

## Core Operations

### 1. Build a Graph from Local Repository

Build an AST-based knowledge graph using tree-sitter and code analysis:

```bash
source venv/bin/activate
cd /path/to/repo

# Full graph build (first time)
gathon build . --full

# With compression enabled (recommended for large repos)
gathon build . --full --compress ultra

# Incremental update (faster for subsequent runs)
gathon update .
```

**What it produces:**
- `.gathon/graph.db` — SQLite database with code structure
- `.gathon/symbols.json` — indexed symbols for fast lookup
- `.gathon/stats.json` — graph statistics and metrics

### 2. Build a Document/Content Graph

For papers, docs, notes, or mixed corpora:

```bash
source venv/bin/activate

# Full pipeline: detect → extract → cluster → visualize
/graphify /path/to/docs

# With specific options:
/graphify /path/to/docs --mode deep             # aggressive inference extraction
/graphify /path/to/docs --obsidian              # generate Obsidian vault
/graphify /path/to/docs --no-viz                # skip visualization
/graphify /path/to/docs --update                # incremental (changed files only)
```

**What it produces:**
- `graphify-out/graph.json` — knowledge graph (nodes + edges)
- `graphify-out/GRAPH_REPORT.md` — audit trail with God Nodes and surprises
- `graphify-out/graph.html` — interactive visualization (browser-based)
- `graphify-out/obsidian/` — Obsidian vault (if --obsidian)

### 3. Fetch and Add External Content

Add URLs (papers, repos, tweets, videos) to your corpus:

```bash
source venv/bin/activate

# Fetch a single URL
/graphify add https://arxiv.org/abs/2301.12345

# Fetch with author/contributor metadata
/graphify add https://github.com/owner/repo --author "Name" --contributor "Name"

# Add tweet/video/PDF automatically (auto-detected):
/graphify add https://twitter.com/user/status/123456  # → fetches via oEmbed
/graphify add https://www.youtube.com/watch?v=xyz    # → transcribes audio
/graphify add https://example.com/paper.pdf          # → downloads PDF
```

After adding, the graph is automatically updated with the new content.

### 4. Cross-Repo Graph Merging

Build and merge graphs from multiple repositories:

```bash
source venv/bin/activate

# Clone repos into ~/.graphify/repos/
graphify clone https://github.com/owner/repo1 --branch main
graphify clone https://github.com/owner/repo2 --branch develop

# Build each repo's graph
/graphify ~/.graphify/repos/owner/repo1
/graphify ~/.graphify/repos/owner/repo2

# Merge into unified graph
graphify merge-graphs \
  ~/.graphify/repos/owner/repo1/graphify-out/graph.json \
  ~/.graphify/repos/owner/repo2/graphify-out/graph.json \
  --out cross-repo-graph.json
```

Result: `cross-repo-graph.json` with a `repo` attribute on every node for filtering by origin.

### 5. Optimize and Compress Graphs

Apply compression and optimization for token efficiency:

```bash
source venv/bin/activate
cd /path/to/repo

# Show current compression stats
gathon compression status

# Enable compression on serve
gathon serve . --compress ultra

# Prefetch optimization
gathon prefetch --budget 4096 --models gpt-4 claude-opus

# Show prefetch stats
gathon prefetch status

# Memory engine optimization
gathon memory status
gathon memory search "pattern_name"
```

### 6. Query and Explore Graphs

Once a graph is built, query it using BFS or DFS traversal:

```bash
source venv/bin/activate

# Broad context (BFS) - "what is X connected to?"
/graphify query "authentication flow"

# Specific path (DFS) - "how does X reach Y?"
/graphify query "login validation" --dfs

# With token budget
/graphify query "database schema" --budget 1500

# Find shortest path between concepts
/graphify path "AuthModule" "Database"

# Explain a single node
/graphify explain "Session Management"
```

### 7. Export Graph in Different Formats

Convert graph to other tools and formats:

```bash
source venv/bin/activate

# Neo4j (for visualization in Neo4j Desktop)
/graphify . --neo4j
# → generates cypher.txt for import

# Push directly to running Neo4j instance
/graphify . --neo4j-push bolt://localhost:7687

# SVG export (embeddable in Notion, GitHub)
/graphify . --svg
# → graph.svg

# GraphML export (Gephi, yEd)
/graphify . --graphml
# → graph.graphml

# Start MCP server for agent access
/graphify . --mcp
```

---

## Installation & Setup

### Prerequisites

```bash
# Python 3.11+
python3 --version

# Create virtual environment (if not already done)
python3 -m venv venv
source venv/bin/activate
```

### Install Packages

```bash
source venv/bin/activate

# Install gathon (code graph engine)
pip install -e .

# Install graphify (document graph engine)
pip install graphifyy

# For video/audio transcription
pip install 'graphifyy[video]'

# For Kimi K2.6 backend (cheaper semantic extraction)
pip install 'graphifyy[kimi]'
```

### Verify Installation

```bash
source venv/bin/activate

# Check gathon
gathon --version
gathon --help

# Check graphify
graphify --help

# Test both together
graphify install
```

---

## Graph Management

### View Graph Statistics

```bash
source venv/bin/activate

# Show nodes, edges, clusters
gathon status

# Detailed symbol index
gathon symbols --list

# Full analysis
gathon status --detailed
```

### Update Graphs Incrementally

After modifying files:

```bash
source venv/bin/activate
cd /path/to/repo

# Fast: only re-extract changed files
gathon update .

# Or with graphify (mixed content):
/graphify . --update
```

### Reset or Rebuild

```bash
# Full rebuild (clears cache)
gathon build . --full

# Or remove and rebuild:
rm -rf .gathon graphify-out/
gathon build .
/graphify .
```

### Monitor Costs

```bash
source venv/bin/activate

# Show token usage
gathon compression telemetry

# Compare with compression disabled
gathon compression baseline
```

---

## Performance Tuning

### Compression Strategies

| Level | Use Case | Reduction |
|-------|----------|-----------|
| `none` | Testing, small repos | 0% |
| `standard` | Default for medium repos | 30-40% |
| `aggressive` | Large repos, budget-conscious | 50-60% |
| `ultra` | Maximum compression, very large repos | 60-70% |

```bash
gathon serve . --compress aggressive
```

### Prefetching Configuration

Predict which tools will be called next and load them ahead of time:

```bash
# Show current prefetch model
gathon prefetch --models claude-opus sonnet

# Tune budget per request
gathon prefetch --budget 2048
```

### Memory Engine

Cache extracted knowledge across sessions:

```bash
# Show memory stats
gathon memory stats

# Search cached knowledge
gathon memory search "auth mechanism"

# Purge old entries
gathon memory purge --days 30
```

---

## Common Workflows

### Workflow A: New Large Repository

```bash
source venv/bin/activate
cd /path/to/repo

# 1. Build compressed graph
gathon build . --full --compress ultra

# 2. Index symbols
gathon symbols --index

# 3. Serve with prefetch
gathon serve . --compress ultra

# 4. Query as needed
/graphify query "main entry point" --dfs
```

### Workflow B: Documentation + Code

```bash
source venv/bin/activate

# 1. Build code graph
gathon build /path/to/code --full

# 2. Build doc graph
/graphify /path/to/docs --obsidian

# 3. Merge
graphify merge-graphs \
  .gathon/graph.json \
  graphify-out/graph.json \
  --out unified-graph.json

# 4. Query unified graph
/graphify query "architecture pattern"
```

### Workflow C: Continuous Development

```bash
# Terminal 1: Watch code changes
source venv/bin/activate
cd /path/to/repo
gathon serve . --compress ultra

# Terminal 2: Auto-update on code changes (optional)
source venv/bin/activate
cd /path/to/repo
/graphify . --watch

# Editor: Make changes, graphs update automatically
```

---

## Troubleshooting

### Graph is Empty

```bash
# Check what files were detected
ls -la .gathon/
cat graphify-out/.graphify_detect.json

# Verify support for file types
gathon --help | grep -i language
```

### Slow Graph Queries

```bash
# Enable compression
gathon serve . --compress ultra

# Check graph size
gathon status --detailed
jq '.stats.node_count' .gathon/stats.json
```

### API Costs High

```bash
# Enable cheaper backend (Kimi instead of Claude)
export MOONSHOT_API_KEY=your_key
/graphify . --mode deep  # Will auto-use Kimi

# Show cost breakdown
gathon compression telemetry
```

### Cache Issues

```bash
# Clear all caches
rm -rf .gathon/cache
rm -rf graphify-out/.graphify_cached.json

# Rebuild from scratch
gathon build . --full
```

---

## Output Files Reference

### Gathon Outputs

| File | Purpose |
|------|---------|
| `.gathon/graph.db` | SQLite database with code structure |
| `.gathon/symbols.json` | Symbol index for fast lookup |
| `.gathon/stats.json` | Graph metrics and node counts |
| `.gathon/manifest.json` | File state for incremental updates |

### Graphify Outputs

| File | Purpose |
|------|---------|
| `graphify-out/graph.json` | Raw graph nodes + edges |
| `graphify-out/GRAPH_REPORT.md` | Markdown audit report |
| `graphify-out/graph.html` | Interactive browser visualization |
| `graphify-out/obsidian/` | Obsidian vault (if --obsidian) |
| `graphify-out/graph.graphml` | Gephi/yEd import format (if --graphml) |
| `graphify-out/cypher.txt` | Neo4j import script (if --neo4j) |

---

## Key Differences: Gathon vs Graphify

| Feature | Gathon | Graphify |
|---------|--------|----------|
| **Input** | Code repositories | Documents, mixed content |
| **Parser** | Tree-sitter (AST) | LLM + vision |
| **Best for** | Code structure, architecture | Concepts, ideas, literature |
| **Speed** | Fast (deterministic) | Medium (requires LLM) |
| **Cost** | Low (no API calls) | Medium (Claude/Kimi calls) |
| **Output** | `graph.db` | `graph.json` |
