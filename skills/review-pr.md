---
description: "When the user asks to review a specific pull request with full context"
---

# Review PR

Full PR review with blast radius and flow analysis.

## Goal
Comprehensive review: what changed, what's impacted, what's risky.

## Tools to use
1. `get_minimal_context` — orient
2. `detect_changes` with PR's changed files
3. `get_impact_radius` — blast radius from changed files
4. `get_affected_flows` — which flows touched
5. `query_graph` pattern=tests_for — check test coverage
6. `get_review_context` — source snippets

## Constraints
- Get changed files from PR (use `gh pr diff` or explicit list).
- Report: summary, risk level, specific concerns, suggested focus areas.

## Gotchas
- Large PRs (50+ files) may hit max_nodes limit — increase if needed.
- Cross-repo PRs won't have graph context for external deps.
