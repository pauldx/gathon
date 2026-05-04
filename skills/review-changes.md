---
description: "When the user asks to review code changes, PRs, or recent commits"
---

# Review Changes

Risk-scored code review using graph context.

## Goal
Identify high-risk changes, untested code paths, and cross-boundary impacts.

## Tools to use
1. `get_minimal_context` — orient
2. `detect_changes` — risk-scored analysis
3. `get_affected_flows` — execution flow impact
4. `get_review_context` — source context per changed file
5. `get_impact_radius` — blast radius

## Constraints
- Focus on risk: what could break, what's untested.
- Flag cross-domain impacts (code changes affecting docs, API spec drift).
- Keep output actionable — specific files and functions, not general advice.

## Gotchas
- `detect_changes` wraps changes module — may return basic results if module unavailable.
- Changed files auto-detected via `git diff HEAD~1` — pass explicit list if different base needed.
