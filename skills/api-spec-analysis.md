---
description: "When the user asks to analyze OpenAPI specs, trace API endpoints, or check spec-code alignment"
---

# API Spec Analysis

OpenAPI-specific: compress → graph → traverse → verify alignment.

## Goal
Analyze API surface area: endpoints, schemas, refs, and alignment with implementation code.

## Tools to use
1. `build_graph` — ensures OpenAPI specs are parsed
2. `semantic_search` query="Endpoint" — find all endpoints
3. `query_graph` pattern=references — trace schema refs from endpoints
4. `shortest_path` — connect endpoint to implementation function
5. `get_surprising_connections` — spec ↔ code alignment gaps

## Constraints
- OpenAPI parser extracts Endpoint and APIResource node kinds.
- Schema cross-refs are REFERENCES edges.
- Alignment = shortest path from endpoint node to code function node.

## Gotchas
- Only YAML/JSON OpenAPI files detected (not Swagger UI HTML).
- Detection heuristic checks for `openapi:` key in first 2KB.
- Deeply nested allOf/oneOf schemas: refs are found recursively but structure is flat.
