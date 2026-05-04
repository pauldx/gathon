---
description: "When the user asks to build a knowledge graph from documents, PDFs, images, or URLs"
---

# Graphify Knowledge

Multi-modal knowledge graph with parallel extraction.

## Goal
Extract knowledge from non-code sources into the unified graph.

## Tools to use
1. `build_graph` — if mixed repo (auto-routes docs to graphify)
2. `ingest_url` — for URLs (YouTube, arXiv, web pages)
3. `list_graph_stats` — verify extraction results
4. `get_surprising_connections` — find cross-domain links

## Constraints
- Document extraction is AST-based (fast). PDF/image may need LLM (slower).
- URL ingestion fetches and processes inline — may be slow for video.

## Gotchas
- Graphify needs API keys for image analysis and video transcription.
- PDF extraction quality varies — check node count after build.
- Large documents (>100 pages) may need chunking.
