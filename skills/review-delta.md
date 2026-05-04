---
description: "When the user asks for an incremental delta review of recent changes"
---

# Review Delta

Quick incremental review — what changed since last check.

## Goal
Fast delta: just the changes, risk-scored, with flow impact.

## Tools to use
1. `detect_changes` — risk score
2. `get_affected_flows` — flow impact
3. `get_impact_radius` — if risk is high

## Constraints
- Keep it fast — 2-3 tool calls max.
- Only escalate to full review if risk score is high.

## Gotchas
- Relies on git diff — won't catch uncommitted changes unless staged.
