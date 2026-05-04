"""Symbol indexing engine with tree-sitter parsing and SQLite storage."""

from .indexer import SymbolIndex
from .models import FileSymbols, ImportInfo, SymbolDependency, SymbolInfo

__all__ = [
    "SymbolIndex",
    "SymbolInfo",
    "SymbolDependency",
    "FileSymbols",
    "ImportInfo",
    "find_symbol",
    "get_function_source",
    "get_class_source",
    "get_symbol_dependencies",
    "get_symbol_dependents",
]

_default_index: SymbolIndex | None = None


def _get_index() -> SymbolIndex:
    global _default_index
    if _default_index is None:
        import os
        root = os.getcwd()
        _default_index = SymbolIndex(project_root=root)
    return _default_index


def find_symbol(name: str, exact: bool = False) -> list[SymbolInfo]:
    """Search for symbols by name using the default project index."""
    return _get_index().find_symbol(name, exact=exact)


def get_function_source(name: str, level: int = 0) -> str:
    """Get function source code. level: 0=full, 1=sig+doc, 2=sig only."""
    return _get_index().get_function_source(name, level=level)


def get_class_source(name: str, level: int = 0) -> str:
    """Get class source code. level: 0=full, 1=sig+methods, 2=sig only."""
    return _get_index().get_class_source(name, level=level)


def get_symbol_dependencies(name: str) -> list[SymbolDependency]:
    """Get what a symbol depends on (calls, imports, inherits)."""
    return _get_index().get_dependencies(name)


def get_symbol_dependents(name: str) -> list[SymbolDependency]:
    """Get what depends on a symbol (callers, importers)."""
    return _get_index().get_dependents(name)
