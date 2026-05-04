"""Token budget tracking for tool responses.

Uses conservative 4 chars/token estimate (matches claude-mem's heuristic).
Attaches _token_meta to tool response dicts so agents can make
cost-aware decisions about fetching additional details.
"""

from __future__ import annotations

import json
from typing import Any

CHARS_PER_TOKEN = 4


def estimate_tokens(data: Any) -> int:
    """Estimate token count for arbitrary data using char-based heuristic."""
    if isinstance(data, str):
        return max(1, len(data) // CHARS_PER_TOKEN)
    if isinstance(data, (int, float, bool)):
        return 1
    if data is None:
        return 0
    text = json.dumps(data, default=str, ensure_ascii=False)
    return max(1, len(text) // CHARS_PER_TOKEN)


def attach_token_meta(data: dict[str, Any]) -> dict[str, Any]:
    """Add _token_meta field to a tool response dict.

    Includes: estimated_tokens, result_count, avg_tokens_per_result.
    Agent uses this to decide whether fetching more details is worth the cost.
    """
    total = estimate_tokens(data)

    result_count = 0
    for key in ("nodes", "results", "edges", "items", "questions",
                "communities", "flows", "functions", "locations"):
        val = data.get(key)
        if isinstance(val, list):
            result_count = len(val)
            break

    if result_count == 0:
        result_count = data.get("count", 0)

    avg = total // result_count if result_count > 0 else total

    data["_token_meta"] = {
        "estimated_tokens": total,
        "result_count": result_count,
        "avg_tokens_per_result": avg,
    }
    return data
