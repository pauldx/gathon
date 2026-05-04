"""ROI (Return on Investment) tracking for memory observations."""

from __future__ import annotations

from datetime import UTC, datetime

from .db import MemoryDB
from .models import IMMUNE_TYPES, Observation


def calculate_roi(obs: Observation) -> float:
    """Calculate ROI score for an observation.

    Formula: access_count * importance * (1 / max(1, days_since_created / 30))

    Higher ROI = more valuable. Combines frequency of use, declared importance,
    and recency into a single score.
    """
    if not obs.created_at:
        return 0.0

    now = datetime.now(UTC)
    try:
        created = datetime.strptime(obs.created_at, "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=UTC
        )
    except ValueError:
        return 0.0

    days_since = max(0, (now - created).days)
    recency_factor = 1.0 / max(1, days_since / 30)

    return obs.access_count * obs.importance * recency_factor


def get_low_roi(db: MemoryDB, threshold: float = 0.1) -> list[Observation]:
    """Return observations with ROI below threshold, excluding immune types."""
    immune_set = {str(t) for t in IMMUNE_TYPES}
    candidates = db.index(limit=500)
    low_roi: list[Observation] = []

    for obs in candidates:
        if obs.obs_type in immune_set:
            continue
        if calculate_roi(obs) < threshold:
            low_roi.append(obs)

    return low_roi


def gc_low_roi(db: MemoryDB, threshold: float = 0.1) -> int:
    """Archive low-ROI observations. Returns count archived."""
    targets = get_low_roi(db, threshold)
    count = 0
    for obs in targets:
        if db.delete(obs.id):
            count += 1
    return count
