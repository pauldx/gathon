"""Cross-session memory engine for gathon.

Provides persistent observation storage with FTS5 search, ROI tracking,
automatic decay/promotion, and contradiction detection.
"""

from .db import MemoryDB
from .models import Observation, ObservationType, SearchResult

__all__ = [
    "MemoryDB",
    "Observation",
    "ObservationType",
    "SearchResult",
    "memory_save",
    "memory_search",
    "memory_index",
    "memory_get",
    "memory_delete",
]


def _default_db() -> MemoryDB:
    """Create a MemoryDB with default path. Caller is responsible for closing."""
    return MemoryDB()


def memory_save(
    obs_type: str,
    title: str,
    content: str,
    importance: float = 0.5,
    project_dir: str = "",
    linked_symbols: list[str] | None = None,
    tags: list[str] | None = None,
) -> int:
    """Save an observation to the default memory database."""
    with _default_db() as db:
        return db.save(
            obs_type=obs_type,
            title=title,
            content=content,
            importance=importance,
            project_dir=project_dir,
            linked_symbols=linked_symbols,
            tags=tags,
        )


def memory_search(
    query: str,
    type_filter: str | None = None,
    limit: int = 10,
    project_dir: str | None = None,
) -> list[SearchResult]:
    """Search the default memory database."""
    with _default_db() as db:
        return db.search(query, type_filter=type_filter, limit=limit, project_dir=project_dir)


def memory_index(
    limit: int = 50,
    type_filter: str | None = None,
) -> list[Observation]:
    """List observations from the default memory database."""
    with _default_db() as db:
        return db.index(limit=limit, type_filter=type_filter)


def memory_get(obs_id: int) -> Observation | None:
    """Get an observation by id from the default memory database."""
    with _default_db() as db:
        return db.get(obs_id)


def memory_delete(obs_id: int) -> bool:
    """Soft-delete an observation from the default memory database."""
    with _default_db() as db:
        return db.delete(obs_id)
