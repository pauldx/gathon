---
description: "When the user asks to explore cross-domain connections between code, docs, and API specs"
---

# Explore Knowledge

Cross-domain queries: code ↔ docs ↔ API specs ↔ configs.

## Goal
Reveal connections that span different content types.

## Tools to use
1. `get_minimal_context` — see what types exist in graph
2. `shortest_path` — trace connections across domains
3. `get_surprising_connections` — auto-detect cross-boundary edges
4. `traverse_graph` — free-form exploration with token budget
5. `god_nodes` scope=document — hub documents

## Constraints
- This skill shines when graph has mixed content (code + docs + specs).
- If graph is code-only, suggest building with docs included.

## Gotchas
- Cross-domain edges are often REFERENCES or SEMANTICALLY_SIMILAR — lower confidence.
- Shortest path is undirected — may traverse unexpected routes.
