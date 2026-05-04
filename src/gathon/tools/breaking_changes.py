"""API breaking change detection by comparing code against a git ref."""

from __future__ import annotations

import ast
import logging
import re
import subprocess
from pathlib import Path
from typing import Any

from gathon.store import UnifiedStore

logger = logging.getLogger(__name__)

_SEVERITY_HIGH = "high"
_SEVERITY_MEDIUM = "medium"


def _project_root(store: UnifiedStore) -> Path:
    """Derive project root from the store's db_path (go up from .gathon/graph.db)."""
    db_path = Path(store.db_path)
    candidate = db_path.parent
    while candidate != candidate.parent:
        if (candidate / ".git").exists():
            return candidate
        candidate = candidate.parent
    return db_path.parent.parent


def _git_run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _extract_python_symbols(source: str) -> dict[str, dict]:
    """Extract function/class signatures from Python source.

    Returns dict of qualified_name -> {kind, params, defaults, return_type, bases, methods}.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}

    symbols: dict[str, dict] = {}

    def _param_names(func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
        args = func_node.args
        names = []
        for a in args.posonlyargs:
            names.append(a.arg)
        for a in args.args:
            names.append(a.arg)
        if args.vararg:
            names.append(f"*{args.vararg.arg}")
        for a in args.kwonlyargs:
            names.append(a.arg)
        if args.kwarg:
            names.append(f"**{args.kwarg.arg}")
        return names

    def _default_count(func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
        args = func_node.args
        return len(args.defaults) + len(args.kw_defaults)

    def _return_annotation(func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
        if func_node.returns:
            return ast.dump(func_node.returns)
        return None

    def _visit_class(node: ast.ClassDef, prefix: str = "") -> None:
        qname = f"{prefix}{node.name}" if prefix else node.name
        bases = [ast.dump(b) for b in node.bases]

        methods: dict[str, dict] = {}
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not item.name.startswith("_") or item.name.startswith("__"):
                    params = _param_names(item)
                    meth_qname = f"{qname}.{item.name}"
                    meth_info = {
                        "kind": "method",
                        "params": params,
                        "defaults": _default_count(item),
                        "return_type": _return_annotation(item),
                    }
                    methods[item.name] = meth_info
                    symbols[meth_qname] = meth_info

        symbols[qname] = {
            "kind": "class",
            "params": [],
            "defaults": 0,
            "return_type": None,
            "bases": bases,
            "methods": methods,
        }

    def _visit_func(node: ast.FunctionDef | ast.AsyncFunctionDef, prefix: str = "") -> None:
        qname = f"{prefix}{node.name}" if prefix else node.name
        params = _param_names(node)
        symbols[qname] = {
            "kind": "function",
            "params": params,
            "defaults": _default_count(node),
            "return_type": _return_annotation(node),
            "bases": [],
            "methods": {},
        }

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            if not node.name.startswith("_"):
                _visit_class(node)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            parent_is_class = False
            for parent in ast.walk(tree):
                if isinstance(parent, ast.ClassDef):
                    for child in parent.body:
                        if child is node:
                            parent_is_class = True
                            break
            if not parent_is_class and not node.name.startswith("_"):
                _visit_func(node)

    return symbols


def _extract_js_symbols(source: str) -> dict[str, dict]:
    """Regex-based symbol extraction for JavaScript/TypeScript."""
    symbols: dict[str, dict] = {}

    for m in re.finditer(
        r"export\s+(?:default\s+)?(?:function|class|const|let|var)\s+(\w+)",
        source,
    ):
        symbols[m.group(1)] = {
            "kind": "export",
            "params": [],
            "defaults": 0,
            "return_type": None,
            "bases": [],
            "methods": {},
        }

    for m in re.finditer(r"module\.exports\s*=\s*(\w+)", source):
        symbols[m.group(1)] = {
            "kind": "export",
            "params": [],
            "defaults": 0,
            "return_type": None,
            "bases": [],
            "methods": {},
        }

    return symbols


def _extract_go_symbols(source: str) -> dict[str, dict]:
    """Regex-based symbol extraction for Go (exported functions only)."""
    symbols: dict[str, dict] = {}

    for m in re.finditer(r"^func\s+(?:\([^)]*\)\s+)?([A-Z]\w*)\s*\(", source, re.MULTILINE):
        symbols[m.group(1)] = {
            "kind": "function",
            "params": [],
            "defaults": 0,
            "return_type": None,
            "bases": [],
            "methods": {},
        }

    return symbols


def _extract_symbols(source: str, file_path: str) -> dict[str, dict]:
    """Dispatch to the right extractor based on file extension."""
    ext = Path(file_path).suffix.lower()
    if ext == ".py":
        return _extract_python_symbols(source)
    if ext in (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"):
        return _extract_js_symbols(source)
    if ext == ".go":
        return _extract_go_symbols(source)
    return {}


def _compare_symbols(
    old_symbols: dict[str, dict],
    new_symbols: dict[str, dict],
    file_path: str,
) -> list[dict[str, Any]]:
    """Compare old vs new symbols and emit breaking change records."""
    changes: list[dict[str, Any]] = []

    for name, old_info in old_symbols.items():
        if name not in new_symbols:
            kind = old_info.get("kind", "function")
            if kind == "class":
                changes.append({
                    "kind": "removed_function",
                    "symbol": name,
                    "file_path": file_path,
                    "old_signature": f"class {name}",
                    "new_signature": None,
                    "severity": _SEVERITY_HIGH,
                    "description": f"Class '{name}' was removed",
                })
                for meth_name in old_info.get("methods", {}):
                    changes.append({
                        "kind": "removed_method",
                        "symbol": f"{name}.{meth_name}",
                        "file_path": file_path,
                        "old_signature": (
                            f"{name}.{meth_name}"
                            f"({', '.join(old_info['methods'][meth_name].get('params', []))})"
                        ),
                        "new_signature": None,
                        "severity": _SEVERITY_HIGH,
                        "description": f"Method '{name}.{meth_name}' removed (class deleted)",
                    })
            else:
                changes.append({
                    "kind": "removed_function",
                    "symbol": name,
                    "file_path": file_path,
                    "old_signature": f"{name}({', '.join(old_info.get('params', []))})",
                    "new_signature": None,
                    "severity": _SEVERITY_HIGH,
                    "description": f"Function '{name}' was removed",
                })
            continue

        new_info = new_symbols[name]

        # Check base class changes
        old_bases = old_info.get("bases", [])
        new_bases = new_info.get("bases", [])
        if old_bases != new_bases:
            changes.append({
                "kind": "changed_bases",
                "symbol": name,
                "file_path": file_path,
                "old_signature": f"class {name}({', '.join(old_bases)})",
                "new_signature": f"class {name}({', '.join(new_bases)})",
                "severity": _SEVERITY_HIGH,
                "description": (
                    f"Inheritance of '{name}' changed "
                    f"from [{', '.join(old_bases)}] to [{', '.join(new_bases)}]"
                ),
            })

        # Check removed methods on classes
        old_methods = old_info.get("methods", {})
        new_methods = new_info.get("methods", {})
        for meth_name, meth_info in old_methods.items():
            if meth_name not in new_methods:
                changes.append({
                    "kind": "removed_method",
                    "symbol": f"{name}.{meth_name}",
                    "file_path": file_path,
                    "old_signature": (
                        f"{name}.{meth_name}"
                        f"({', '.join(meth_info.get('params', []))})"
                    ),
                    "new_signature": None,
                    "severity": _SEVERITY_HIGH,
                    "description": f"Public method '{name}.{meth_name}' was removed",
                })

        # Check parameter changes for functions and methods
        if old_info.get("kind") in ("function", "method"):
            old_params = old_info.get("params", [])
            new_params = new_info.get("params", [])
            old_defaults = old_info.get("defaults", 0)
            new_defaults = new_info.get("defaults", 0)

            old_sig = f"{name}({', '.join(old_params)})"
            new_sig = f"{name}({', '.join(new_params)})"

            # Removed parameters
            old_set = set(old_params)
            new_set = set(new_params)
            removed = old_set - new_set
            if removed:
                changes.append({
                    "kind": "removed_parameter",
                    "symbol": name,
                    "file_path": file_path,
                    "old_signature": old_sig,
                    "new_signature": new_sig,
                    "severity": _SEVERITY_HIGH,
                    "description": f"Parameter(s) {removed} removed from '{name}'",
                })

            # Added required parameters (new params without defaults)
            added = new_set - old_set
            if added:
                new_required_count = len(new_params) - new_defaults
                old_required_count = len(old_params) - old_defaults
                if new_required_count > old_required_count:
                    changes.append({
                        "kind": "added_required_param",
                        "symbol": name,
                        "file_path": file_path,
                        "old_signature": old_sig,
                        "new_signature": new_sig,
                        "severity": _SEVERITY_HIGH,
                        "description": f"New required parameter(s) added to '{name}'",
                    })

            # Return type changes
            old_ret = old_info.get("return_type")
            new_ret = new_info.get("return_type")
            if old_ret and new_ret and old_ret != new_ret:
                changes.append({
                    "kind": "changed_signature",
                    "symbol": name,
                    "file_path": file_path,
                    "old_signature": f"{old_sig} -> {old_ret}",
                    "new_signature": f"{new_sig} -> {new_ret}",
                    "severity": _SEVERITY_MEDIUM,
                    "description": f"Return type of '{name}' changed",
                })

    return changes


def detect_breaking_changes(
    store: UnifiedStore,
    since_ref: str = "HEAD~1",
    file_patterns: list[str] | None = None,
) -> dict[str, Any]:
    """Detect breaking API changes by comparing current code against a git ref.

    Uses AST parsing for Python, regex for JS/TS/Go. Returns structured report
    of removed functions, changed signatures, removed methods, etc.
    """
    root = _project_root(store)

    # Verify git repo
    result = _git_run(["rev-parse", "--git-dir"], cwd=root)
    if result.returncode != 0:
        return {
            "ref": since_ref,
            "error": "Not a git repository",
            "breaking_changes": [],
            "files_analyzed": 0,
            "total_breaking": 0,
            "by_severity": {"high": 0, "medium": 0},
        }

    # Verify ref exists
    result = _git_run(["rev-parse", "--verify", since_ref], cwd=root)
    if result.returncode != 0:
        return {
            "ref": since_ref,
            "error": f"Git ref '{since_ref}' does not exist",
            "breaking_changes": [],
            "files_analyzed": 0,
            "total_breaking": 0,
            "by_severity": {"high": 0, "medium": 0},
        }

    # Get changed files
    diff_result = _git_run(["diff", "--name-only", since_ref], cwd=root)
    if diff_result.returncode != 0:
        return {
            "ref": since_ref,
            "error": f"git diff failed: {diff_result.stderr.strip()}",
            "breaking_changes": [],
            "files_analyzed": 0,
            "total_breaking": 0,
            "by_severity": {"high": 0, "medium": 0},
        }

    changed_files = [f for f in diff_result.stdout.strip().splitlines() if f]

    # Filter by patterns if provided
    if file_patterns:
        filtered = []
        for fp in changed_files:
            for pattern in file_patterns:
                if re.search(pattern, fp):
                    filtered.append(fp)
                    break
        changed_files = filtered

    all_changes: list[dict[str, Any]] = []
    files_analyzed = 0

    for file_path in changed_files:
        ext = Path(file_path).suffix.lower()
        if ext not in (".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".go"):
            continue

        # Get old version from git
        show_result = _git_run(["show", f"{since_ref}:{file_path}"], cwd=root)
        if show_result.returncode != 0:
            continue
        old_source = show_result.stdout

        # Get new version from working tree
        full_path = root / file_path
        if not full_path.exists():
            # File was deleted entirely — extract all old symbols as removed
            old_symbols = _extract_symbols(old_source, file_path)
            new_symbols: dict[str, dict] = {}
        else:
            try:
                new_source = full_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            old_symbols = _extract_symbols(old_source, file_path)
            new_symbols = _extract_symbols(new_source, file_path)

        files_analyzed += 1
        file_changes = _compare_symbols(old_symbols, new_symbols, file_path)
        all_changes.extend(file_changes)

    by_severity = {"high": 0, "medium": 0}
    for change in all_changes:
        sev = change.get("severity", _SEVERITY_MEDIUM)
        by_severity[sev] = by_severity.get(sev, 0) + 1

    return {
        "ref": since_ref,
        "breaking_changes": all_changes,
        "files_analyzed": files_analyzed,
        "total_breaking": len(all_changes),
        "by_severity": by_severity,
    }
