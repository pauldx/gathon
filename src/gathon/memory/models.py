"""Memory observation models and type definitions."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class ObservationType(StrEnum):
    USER = "user"
    FEEDBACK = "feedback"
    PROJECT = "project"
    REFERENCE = "reference"
    GUARDRAIL = "guardrail"
    ERROR_PATTERN = "error_pattern"
    DECISION = "decision"
    CONVENTION = "convention"
    BUGFIX = "bugfix"
    WARNING = "warning"
    NOTE = "note"


# Types immune to decay — never auto-archived
IMMUNE_TYPES = frozenset(
    {ObservationType.GUARDRAIL, ObservationType.CONVENTION, ObservationType.WARNING}
)

# TTL in days per type
TYPE_TTL: dict[str, int] = {
    "note": 60,
    "error_pattern": 90,
    "bugfix": 90,
    "decision": 120,
    "reference": 180,
    "project": 90,
    "user": 365,
    "feedback": 365,
    "guardrail": 999999,
    "convention": 999999,
    "warning": 999999,
}


@dataclass
class Observation:
    id: int = 0
    obs_type: str = "note"
    title: str = ""
    content: str = ""
    importance: float = 0.5
    access_count: int = 0
    last_accessed: str = ""
    created_at: str = ""
    updated_at: str = ""
    archived: bool = False
    project_dir: str = ""
    linked_symbols: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


@dataclass
class SearchResult:
    observation: Observation
    score: float = 0.0
    snippet: str = ""
