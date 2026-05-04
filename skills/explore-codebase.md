---
description: "When the user asks to explore, navigate, or understand the codebase structure"
---

# Explore Codebase

Navigate code via communities, flows, callers, and structural queries.

## Goal
Help user build mental model of codebase. Start broad, drill into specifics.

## Tools to use
1. `get_minimal_context` — orient (always start here)
2. `get_architecture_overview` — community structure
3. `query_graph` — trace relationships (callers_of, callees_of, imports_of)
4. `list_flows` — execution paths
5. `god_nodes` — hub components

## Constraints
- Always start with `get_minimal_context` — costs ~100 tokens.
- Use `detail_level: "minimal"` unless more detail requested.
- Target ≤5 tool calls per question.

## Gotchas
- Graph must exist first — check and suggest `build_graph` if empty.
- Communities require `run_postprocess` — may be empty on fresh build.
