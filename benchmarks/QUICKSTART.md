# Benchmarks — Quick Start

Measure token savings from knowledge graph on any codebase.

## 3 Ways to Run

### 1. Claude Inline Context (Easiest)

In Claude Code session:

```
/benchmark @~/my_project
/benchmark @/path/to/code --models claude-opus-4-7 claude-sonnet-4-6 claude-haiku-4-5-20251001
```

Pass target as `@path`. Benchmark runs in-session, shows results.

### 2. Shell Script

```bash
./benchmarks/run_benchmark.sh ~/my_project
./benchmarks/run_benchmark.sh @~/my_project --models claude-opus-4-7 claude-sonnet-4-6
```

Outputs to `benchmarks/results/benchmark_*.json`

### 3. Python Direct

```bash
python benchmarks/benchmark_runner.py ~/my_project \
  --output-dir benchmarks/results \
  --models claude-opus-4-7 claude-sonnet-4-6
```

## What Happens

```
┌─────────────────────────┐
│ Target Code Directory   │
│  (e.g., ~/my_project)   │
└────────────┬────────────┘
             │
             ↓
┌─────────────────────────┐
│ 1. Scan Files           │
│ (.py, .md, .json, etc)  │
└────────────┬────────────┘
             │
             ↓
┌─────────────────────────┐
│ 2. Build Knowledge Graph│
│ (692+ nodes, 4876 edges)│
└────────────┬────────────┘
             │
             ↓
┌─────────────────────────┐
│ 3. Estimate Tokens      │
│ Pre-graph vs Post-graph │
└────────────┬────────────┘
             │
             ↓
┌─────────────────────────┐
│ 4. Calculate Savings    │
│ Cost by Claude model    │
└────────────┬────────────┘
             │
             ↓
┌─────────────────────────┐
│ 5. Show Report          │
│ Token & $ savings       │
│ Save JSON results       │
└─────────────────────────┘
```

## Example Output

```
================================================================================
                            BENCHMARK RESULTS
================================================================================

Target: /Users/debashispaul/GIT/gathon/src
Timestamp: 2026-05-03 17:12:35

Graph Build: 1664ms
  Nodes: 692
  Edges: 4,876

Token Savings (all queries, all models):
  Before graph: 66,640 tokens
  After graph:  58,000 tokens
  Saved:        8,640 tokens (13.0%)

Cost Savings by Model:
  Claude 3.5 Opus:
    Before: $0.8718
    After:  $0.6810
    Saved:  $0.1908 (21.9%)
  Claude 3.5 Sonnet:
    Before: $0.2488
    After:  $0.1854
    Saved:  $0.0634 (25.5%)

================================================================================
```

## Next Steps

### Analyze Results

```bash
python benchmarks/analyze_results.py benchmarks/results/benchmark_src_*.json
```

Shows per-query and per-model breakdown.

### Custom Queries

Edit `benchmarks/queries/sample_queries.json`:

```json
{
  "id": "q_custom",
  "title": "Your Question",
  "query": "What...",
  "context": "category"
}
```

Re-run benchmark. New queries included.

### Compare Multiple Codebases

```bash
./benchmarks/run_benchmark.sh ~/project1
./benchmarks/run_benchmark.sh ~/project2
./benchmarks/run_benchmark.sh ~/project3

# Then compare results:
ls -lh benchmarks/results/
```

## Benchmark Metrics

| Metric | Meaning |
|--------|---------|
| **Graph Build** | Time to extract code + docs |
| **Nodes** | Code entities (files, classes, functions, sections) |
| **Edges** | Relationships (calls, contains, imports, etc.) |
| **Token Savings** | Fewer tokens needed post-graph |
| **Cost Savings** | $ reduction per model |

## Models & Pricing (May 2026)

| Model | Input | Output |
|-------|-------|--------|
| Opus | $15/M | $45/M |
| Sonnet | $3/M | $15/M |
| Haiku | $0.80/M | $4/M |

Graph-guided queries often best with **Haiku** (cheaper + focused).

## Tips

- Larger codebases show bigger token savings (more context to compress)
- Architecture queries benefit most (need full understanding)
- Results stored as JSON for integration with CI/CD
- No API key needed (uses token estimation, not actual calls)

## Docs

- `README.md` — Full documentation & customization
- `SKILL.md` — Claude command reference
- `benchmark_runner.py` — Implementation details
- `queries/sample_queries.json` — Query definitions

---

Ready to benchmark? Run:

```bash
/benchmark @.
```

(uses current directory)
