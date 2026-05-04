"""Greedy fractional knapsack for context packing within token budgets."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from gathon.tokens import estimate_tokens


@dataclass
class ContextCandidate:
    """A candidate chunk of context competing for token budget."""

    name: str
    content: str
    token_cost: int
    relevance: float = 0.0       # 0.0-1.0
    dep_distance: int = 0        # graph distance from target, 0=direct
    recency_days: float = 0.0    # days since last access/edit
    access_count: int = 0        # times accessed in session
    kind: str = "function"       # function, class, file, doc, import


@dataclass
class PackedContext:
    """Result of packing candidates into a token budget."""

    candidates: list[ContextCandidate] = field(default_factory=list)
    total_tokens: int = 0
    budget_used_pct: float = 0.0
    items_packed: int = 0
    items_skipped: int = 0


def score_candidate(c: ContextCandidate, query: str = "") -> float:
    """Score a candidate using weighted signals.

    Combines relevance, dependency distance, recency, and access frequency.
    Optionally adds a Jaccard similarity bonus when a query is provided.
    """
    score = (
        0.4 * c.relevance
        + 0.25 * (1.0 / (1.0 + c.dep_distance))
        + 0.2 * (1.0 / (1.0 + c.recency_days / 30.0))
        + 0.15 * min(c.access_count / 10.0, 1.0)
    )

    if query:
        query_words = set(query.lower().split())
        name_words = set(
            c.name.lower().replace("_", " ").replace(".", " ").split()
        )
        jaccard = len(query_words & name_words) / max(
            len(query_words | name_words), 1
        )
        score += 0.1 * jaccard

    return score


def pack_context(
    candidates: list[ContextCandidate],
    budget_tokens: int,
    query: str = "",
) -> PackedContext:
    """Greedy knapsack packing of candidates into a token budget.

    Scores each candidate, sorts by value density (score / token_cost),
    and greedily selects whole candidates that fit the remaining budget.
    """
    if not candidates or budget_tokens <= 0:
        return PackedContext(
            items_skipped=len(candidates),
        )

    scored = [
        (c, score_candidate(c, query)) for c in candidates
    ]

    # value density = score per token
    ranked = sorted(
        scored,
        key=lambda pair: pair[1] / max(pair[0].token_cost, 1),
        reverse=True,
    )

    result = PackedContext()
    remaining = budget_tokens

    for c, _score in ranked:
        if c.token_cost <= remaining:
            result.candidates.append(c)
            result.total_tokens += c.token_cost
            result.items_packed += 1
            remaining -= c.token_cost
        else:
            result.items_skipped += 1

    result.budget_used_pct = (
        (result.total_tokens / budget_tokens) * 100.0
        if budget_tokens > 0
        else 0.0
    )

    return result


def auto_pack(
    symbols: list[dict[str, Any]],
    budget: int = 4000,
    query: str = "",
) -> PackedContext:
    """Convert raw symbol dicts to ContextCandidates and pack them.

    Each dict should have at minimum ``name`` and ``content``.
    Optional keys: ``kind``, ``relevance``, ``dep_distance``,
    ``recency_days``, ``access_count``.
    """
    candidates: list[ContextCandidate] = []

    for sym in symbols:
        content = sym.get("content", "")
        token_cost = estimate_tokens(content)

        candidates.append(
            ContextCandidate(
                name=sym.get("name", "unknown"),
                content=content,
                token_cost=token_cost,
                relevance=float(sym.get("relevance", 0.0)),
                dep_distance=int(sym.get("dep_distance", 0)),
                recency_days=float(sym.get("recency_days", 0.0)),
                access_count=int(sym.get("access_count", 0)),
                kind=sym.get("kind", "function"),
            )
        )

    return pack_context(candidates, budget, query)
