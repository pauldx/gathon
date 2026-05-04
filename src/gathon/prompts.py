"""MCP prompt templates for gathon."""

from __future__ import annotations


def review_changes_prompt(base: str = "HEAD~1") -> list[dict]:
    """Prompt: review recent changes with graph context."""
    return [
        {
            "role": "user",
            "content": (
                f"Review changes since {base}. Use these gathon tools in order:\n"
                "1. `get_minimal_context` — orient yourself\n"
                "2. `detect_changes` — get risk-scored analysis\n"
                "3. `get_affected_flows` — check execution impact\n"
                "4. `get_review_context` — get source context\n\n"
                "Focus on: high-risk changes, untested code, "
                "cross-boundary impacts (code ↔ docs ↔ API specs)."
            ),
        },
    ]


def architecture_map_prompt() -> list[dict]:
    """Prompt: generate architecture overview."""
    return [
        {
            "role": "user",
            "content": (
                "Map this codebase architecture using gathon:\n"
                "1. `get_minimal_context` — overall stats\n"
                "2. `get_architecture_overview` — community structure\n"
                "3. `god_nodes` — hub components\n"
                "4. `get_bridge_nodes` — structural bridges\n"
                "5. `get_surprising_connections` — cross-domain links\n\n"
                "Produce a layered architecture summary with key "
                "components, their responsibilities, and connections."
            ),
        },
    ]


def debug_issue_prompt(description: str = "") -> list[dict]:
    """Prompt: debug an issue using graph traversal."""
    desc = description or "the reported issue"
    return [
        {
            "role": "user",
            "content": (
                f"Debug {desc} using gathon:\n"
                "1. `semantic_search` — find relevant nodes\n"
                "2. `query_graph` with callers_of — trace call chain\n"
                "3. `get_impact_radius` — check blast radius\n"
                "4. `shortest_path` — find connection between "
                "suspected components\n\n"
                "Report: root cause hypothesis, affected components, "
                "suggested fix location."
            ),
        },
    ]


def onboard_developer_prompt() -> list[dict]:
    """Prompt: onboard a new developer."""
    return [
        {
            "role": "user",
            "content": (
                "Onboard me to this codebase using gathon:\n"
                "1. `get_minimal_context` — what's here\n"
                "2. `list_graph_stats` — size and shape\n"
                "3. `get_architecture_overview` — structure\n"
                "4. `list_flows` — key execution paths\n"
                "5. `god_nodes` — most important components\n\n"
                "Give me a 5-minute tour: what the repo does, "
                "how it's organized, where to start reading."
            ),
        },
    ]


def pre_merge_check_prompt(base: str = "HEAD~1") -> list[dict]:
    """Prompt: pre-merge safety check."""
    return [
        {
            "role": "user",
            "content": (
                f"Pre-merge check against {base}:\n"
                "1. `detect_changes` — risk score\n"
                "2. `get_affected_flows` — flow impact\n"
                "3. `get_knowledge_gaps` — untested areas\n"
                "4. `get_impact_radius` — blast radius\n\n"
                "Verdict: SAFE / NEEDS_REVIEW / RISKY with reasons."
            ),
        },
    ]
