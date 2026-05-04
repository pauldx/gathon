"""Advanced search helpers for the memory engine."""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from .db import MemoryDB
from .models import Observation, SearchResult

# Contradiction signal pairs — if an observation mentions one side
# and another mentions the opposite for the same subject, they may conflict.
_OPPOSITION_PAIRS: list[tuple[str, str]] = [
    ("always", "never"),
    ("use", "avoid"),
    ("enable", "disable"),
    ("allow", "deny"),
    ("require", "optional"),
    ("prefer", "avoid"),
    ("include", "exclude"),
    ("must", "must not"),
    ("should", "should not"),
    ("do", "don't"),
    ("do", "do not"),
    ("add", "remove"),
    ("true", "false"),
    ("yes", "no"),
]


def hybrid_search(
    db: MemoryDB,
    query: str,
    type_filter: str | None = None,
    limit: int = 10,
) -> list[SearchResult]:
    """BM25 FTS5 search as primary, supplemented with fuzzy matching if needed."""
    fts_results = db.search(query, type_filter=type_filter, limit=limit)

    if len(fts_results) >= limit:
        return fts_results

    seen_ids = {r.observation.id for r in fts_results}
    remaining = limit - len(fts_results)

    candidates = db.index(limit=200, type_filter=type_filter)
    query_lower = query.lower()
    fuzzy_hits: list[tuple[float, Observation]] = []

    for obs in candidates:
        if obs.id in seen_ids:
            continue
        haystack = f"{obs.title} {obs.obs_type}".lower()
        ratio = SequenceMatcher(None, query_lower, haystack).ratio()
        if ratio >= 0.6:
            fuzzy_hits.append((ratio, obs))

    fuzzy_hits.sort(key=lambda x: -x[0])

    for ratio, obs in fuzzy_hits[:remaining]:
        # Fetch full observation to get content
        full_obs = db.get(obs.id)
        if full_obs is None:
            continue
        fts_results.append(SearchResult(
            observation=full_obs,
            score=ratio,
            snippet=full_obs.content[:120] + ("..." if len(full_obs.content) > 120 else ""),
        ))

    return fts_results


def _extract_subjects(text: str) -> set[str]:
    """Extract potential subject tokens from text (nouns/identifiers)."""
    tokens = re.findall(r"[a-zA-Z_][a-zA-Z0-9_.-]*", text.lower())
    stop_words = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been",
        "being", "have", "has", "had", "do", "does", "did", "will",
        "would", "could", "should", "may", "might", "shall", "can",
        "to", "of", "in", "for", "on", "with", "at", "by", "from",
        "as", "into", "through", "during", "before", "after", "it",
        "this", "that", "these", "those", "and", "or", "but", "not",
        "if", "then", "else", "when", "where", "how", "what", "which",
        "who", "whom", "why", "all", "each", "every", "both", "few",
        "more", "most", "other", "some", "such", "no", "only", "own",
        "same", "so", "than", "too", "very", "just",
    }
    return {t for t in tokens if t not in stop_words and len(t) > 2}


def find_contradictions(db: MemoryDB, obs_id: int) -> list[Observation]:
    """Find observations that might contradict the given observation.

    Uses keyword heuristics: looks for opposition pairs (e.g. "use X" vs "avoid X")
    applied to the same subject tokens.
    """
    target = db.get(obs_id)
    if target is None:
        return []

    target_text = f"{target.title} {target.content}".lower()
    target_subjects = _extract_subjects(target_text)

    if not target_subjects:
        return []

    # Determine which opposition signals the target uses
    target_signals: dict[str, str] = {}
    for pos, neg in _OPPOSITION_PAIRS:
        if pos in target_text:
            target_signals[pos] = neg
        if neg in target_text:
            target_signals[neg] = pos

    if not target_signals:
        return []

    candidates = db.index(limit=200)
    contradictions: list[Observation] = []

    for candidate in candidates:
        if candidate.id == obs_id:
            continue

        full = db.get(candidate.id)
        if full is None or full.archived:
            continue

        cand_text = f"{full.title} {full.content}".lower()
        cand_subjects = _extract_subjects(cand_text)

        shared_subjects = target_subjects & cand_subjects
        if not shared_subjects:
            continue

        for signal, opposite in target_signals.items():
            if opposite in cand_text:
                contradictions.append(full)
                break

    return contradictions
