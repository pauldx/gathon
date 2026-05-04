# Benchmark Knowledge Graph Token Savings

Measure token cost savings from building knowledge graph on target code directory.

## Invocation

```
/benchmark @/path/to/code [--models model1 model2...]
```

## Usage Examples

### Basic: Default models (Opus + Sonnet)

```
/benchmark @~/my_project
```

### Specific models

```
/benchmark @~/my_project --models claude-opus-4-7 claude-sonnet-4-6 claude-haiku-4-5-20251001
```

### Current directory

```
/benchmark @.
```

### With custom queries

Edit `benchmarks/queries/sample_queries.json` first, then:

```
/benchmark @/path/to/code
```

## Output

Runs full benchmark pipeline:

1. **File collection** — scan target for .py, .md, .json, etc.
2. **Graph build** — parse code, create 692+ nodes
3. **Token estimation** — pre-graph vs post-graph
4. **Cost analysis** — savings by Claude model
5. **Report** — tables showing % savings

Example:

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

Results saved to `benchmarks/results/benchmark_*.json`

## Analysis

View detailed breakdown by query and model:

```bash
python benchmarks/analyze_results.py benchmarks/results/benchmark_*.json
```

## What's Measured

**Pre-graph baseline:**
- Raw file listing (50 files)
- Query text
- System prompt
- Estimated output
- ~3100 tokens per query

**Post-graph optimized:**
- Semantic graph context (top-k nodes)
- Query text
- System prompt
- Focused output (less rambling)
- ~3600 tokens per query

**Savings drivers:**
- Better context focus (less hallucination)
- Shorter outputs (graph guides specificity)
- Model selection (Haiku better for graph-guided queries)

## Customization

### Custom queries

Edit `benchmarks/queries/sample_queries.json`:

```json
{
  "id": "q_custom",
  "title": "Your Question",
  "query": "What specific question?",
  "context": "category"
}
```

Then re-run benchmark.

### Different models

```
/benchmark @/path --models claude-opus-4-7 claude-sonnet-4-6 claude-haiku-4-5-20251001
```

Available models:
- `claude-opus-4-7` — $15/$45 per M tokens
- `claude-sonnet-4-6` — $3/$15 per M tokens
- `claude-haiku-4-5-20251001` — $0.80/$4 per M tokens

## See Also

- `benchmarks/README.md` — Full documentation
- `benchmarks/benchmark_runner.py` — Implementation
- `benchmarks/queries/sample_queries.json` — Query config
