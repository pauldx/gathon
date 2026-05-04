---
description: "When the user asks to rename, find dead code, or plan refactoring"
---

# Refactor Safely

Rename preview, dead code detection, impact validation.

## Goal
Safe refactoring with full impact analysis before changes.

## Tools to use
1. `refactor` mode=rename — preview all affected locations
2. `refactor` mode=dead_code — find unreferenced code
3. `refactor` mode=suggest — AI-suggested improvements
4. `get_impact_radius` — verify blast radius of proposed change
5. `find_large_functions` — candidates for extraction

## Constraints
- Always preview before applying. Show user what will change.
- Check test coverage of affected code before refactoring.

## Gotchas
- Rename preview uses qualified names — may miss dynamic references.
- Dead code detection can false-positive on entry points, CLI handlers, event listeners.
