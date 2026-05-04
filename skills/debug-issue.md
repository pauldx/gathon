---
description: "When the user asks to debug an issue, trace a bug, or find root cause"
---

# Debug Issue

Search + flow trace + recent changes to find root cause.

## Goal
Find likely root cause by tracing graph relationships from symptoms to source.

## Tools to use
1. `semantic_search` — find nodes matching error/symptom keywords
2. `query_graph` callers_of — trace call chain upstream
3. `get_impact_radius` — what's connected to suspect
4. `shortest_path` — connection between suspected components
5. `detect_changes` — recent changes near the suspect

## Constraints
- Start from user's description, not from graph structure.
- Report: hypothesis, evidence path, suggested fix location.

## Gotchas
- Search is FTS5-based — exact matches work better than fuzzy.
- Shortest path uses undirected graph — direction may not match call flow.
