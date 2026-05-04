---
description: "When the user asks to build, index, or update the knowledge graph for a repository"
---

# Build Graph

Build or update the unified knowledge graph for the current repository.

## Goal
Produce an up-to-date graph covering code, docs, API specs, and configs — all in one SQLite store.

## Tools to use
1. `build_graph` — adaptive routing, incremental by default
2. `run_postprocess` — flows, communities, FTS indexes
3. `list_graph_stats` — verify results

## Constraints
- Default to incremental (faster). Use `full_rebuild: true` only if user requests or graph is corrupted.
- Report: files parsed, nodes/edges created, any errors.

## Gotchas
- First build on large repo can take minutes — warn user.
- OpenAPI detection is heuristic (checks for `openapi:` key) — may miss non-standard specs.
- Graphify PDF/image extraction requires LLM calls — may fail without API keys.
