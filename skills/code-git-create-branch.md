---
description: "Create a new git branch with a standardized naming convention: numeric_prefix-short_description_with_underscores"
---

# Code Git Create Branch

Create a new local git branch following the standardized naming convention.

## Goal
Generate and checkout a new branch with the format: `{numeric_prefix}-{description_with_underscores}`

## Tools to use
1. `git branch` — create new branch
2. `git checkout` — switch to new branch (or use `git checkout -b` to do both)
3. Validate branch name format before creation

## Constraints
- Branch name must start with a numeric prefix (0-99)
- Followed by a hyphen (-)
- Followed by a short description in snake_case (words separated by underscores)
- No spaces or special characters allowed
- Keep description concise (max 50 characters total)

## Gotchas
- Branch names are case-sensitive in git
- Ensure you're on the correct parent branch before creating new branches
- If branch already exists, user will be prompted before overwriting
- Special characters like `@`, `*`, `?`, `[`, `]` are invalid in branch names
