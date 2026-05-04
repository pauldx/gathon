"""Program slicer: backward slice via AST-based def-use analysis (Weiser 1981 approx)."""

from __future__ import annotations

import ast
import os
from collections import deque
from typing import Any


def _build_def_use_chains(tree: ast.Module) -> tuple[dict[str, list[int]], dict[int, set[str]]]:
    """Build definition and use chains from an AST.

    Returns:
        (definitions, uses) where:
        - definitions: variable name -> list of line numbers where it's assigned
        - uses: line number -> set of variable names used in that statement
    """
    definitions: dict[str, list[int]] = {}
    uses: dict[int, set[str]] = {}

    class _DefUseVisitor(ast.NodeVisitor):

        def _record_def(self, name: str, lineno: int) -> None:
            definitions.setdefault(name, []).append(lineno)

        def _record_uses_from_node(self, node: ast.AST, lineno: int) -> None:
            """Walk a sub-expression to find all Name loads."""
            for child in ast.walk(node):
                if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load):
                    uses.setdefault(lineno, set()).add(child.id)

        def visit_Assign(self, node: ast.Assign) -> None:
            line = node.lineno
            # Record uses from the right side
            self._record_uses_from_node(node.value, line)
            # Record definitions from the left side
            for target in node.targets:
                for name_node in ast.walk(target):
                    if isinstance(name_node, ast.Name) and isinstance(name_node.ctx, ast.Store):
                        self._record_def(name_node.id, line)
            self.generic_visit(node)

        def visit_AugAssign(self, node: ast.AugAssign) -> None:
            line = node.lineno
            self._record_uses_from_node(node.value, line)
            if isinstance(node.target, ast.Name):
                # AugAssign both reads and writes
                uses.setdefault(line, set()).add(node.target.id)
                self._record_def(node.target.id, line)
            self.generic_visit(node)

        def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
            line = node.lineno
            if node.value:
                self._record_uses_from_node(node.value, line)
            if isinstance(node.target, ast.Name) and isinstance(node.target.ctx, ast.Store):
                self._record_def(node.target.id, line)
            self.generic_visit(node)

        def visit_For(self, node: ast.For) -> None:
            line = node.lineno
            self._record_uses_from_node(node.iter, line)
            for name_node in ast.walk(node.target):
                if isinstance(name_node, ast.Name) and isinstance(name_node.ctx, ast.Store):
                    self._record_def(name_node.id, line)
            self.generic_visit(node)

        def visit_With(self, node: ast.With) -> None:
            line = node.lineno
            for item in node.items:
                self._record_uses_from_node(item.context_expr, line)
                if item.optional_vars:
                    for name_node in ast.walk(item.optional_vars):
                        if isinstance(name_node, ast.Name) and isinstance(name_node.ctx, ast.Store):
                            self._record_def(name_node.id, line)
            self.generic_visit(node)

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            line = node.lineno
            self._record_def(node.name, line)
            # Record default value uses
            for default in node.args.defaults + node.args.kw_defaults:
                if default:
                    self._record_uses_from_node(default, line)
            self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self.visit_FunctionDef(node)  # type: ignore[arg-type]

        def visit_Import(self, node: ast.Import) -> None:
            for alias in node.names:
                name = alias.asname if alias.asname else alias.name.split(".")[0]
                self._record_def(name, node.lineno)

        def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
            for alias in node.names:
                name = alias.asname if alias.asname else alias.name
                self._record_def(name, node.lineno)

        def visit_Return(self, node: ast.Return) -> None:
            if node.value:
                self._record_uses_from_node(node.value, node.lineno)

        def visit_Expr(self, node: ast.Expr) -> None:
            self._record_uses_from_node(node.value, node.lineno)
            self.generic_visit(node)

        def visit_If(self, node: ast.If) -> None:
            self._record_uses_from_node(node.test, node.lineno)
            self.generic_visit(node)

        def visit_While(self, node: ast.While) -> None:
            self._record_uses_from_node(node.test, node.lineno)
            self.generic_visit(node)

        def visit_Assert(self, node: ast.Assert) -> None:
            self._record_uses_from_node(node.test, node.lineno)
            if node.msg:
                self._record_uses_from_node(node.msg, node.lineno)

        def visit_Raise(self, node: ast.Raise) -> None:
            if node.exc:
                self._record_uses_from_node(node.exc, node.lineno)

        def visit_Delete(self, node: ast.Delete) -> None:
            for target in node.targets:
                self._record_uses_from_node(target, node.lineno)

        def visit_Global(self, node: ast.Global) -> None:
            for name in node.names:
                self._record_def(name, node.lineno)

        def visit_Nonlocal(self, node: ast.Nonlocal) -> None:
            for name in node.names:
                self._record_def(name, node.lineno)

    _DefUseVisitor().visit(tree)
    return definitions, uses


def _find_enclosing_control(tree: ast.Module, line: int) -> list[int]:
    """Find if/for/while/with statements that enclose a given line.

    Returns their line numbers.
    """
    enclosing: list[int] = []
    control_types = (ast.If, ast.For, ast.While, ast.With, ast.AsyncFor, ast.AsyncWith)

    def _walk_body(nodes: list[ast.stmt], parent_line: int | None = None) -> None:
        for node in nodes:
            if isinstance(node, control_types):
                node_start = node.lineno
                node_end = node.end_lineno or node.lineno
                if node_start <= line <= node_end and node_start != line:
                    enclosing.append(node_start)
                # Recurse into body/orelse
                if hasattr(node, "body"):
                    _walk_body(node.body, node.lineno)
                if hasattr(node, "orelse"):
                    _walk_body(node.orelse, node.lineno)
                if hasattr(node, "handlers"):
                    for handler in node.handlers:
                        _walk_body(handler.body, node.lineno)
                if hasattr(node, "finalbody"):
                    _walk_body(node.finalbody, node.lineno)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if hasattr(node, "body"):
                    _walk_body(node.body)
            elif isinstance(node, ast.Try):
                _walk_body(node.body)
                _walk_body(node.orelse)
                _walk_body(node.finalbody)
                for handler in node.handlers:
                    _walk_body(handler.body)

    _walk_body(tree.body)
    return sorted(set(enclosing))


def _get_uses_at_line(tree: ast.Module, line: int) -> set[str]:
    """Get all variable names used (loaded) at a specific line."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if hasattr(node, "lineno") and node.lineno == line:
            for child in ast.walk(node):
                if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load):
                    names.add(child.id)
    return names


def _text_based_fallback(
    source: str,
    file_path: str,
    variable: str,
    target_line: int,
) -> dict[str, Any]:
    """Simple text-based slice when AST parsing fails."""
    lines = source.splitlines()
    total_lines = len(lines)
    occurrences: list[int] = []

    for i, line_text in enumerate(lines, start=1):
        if variable in line_text:
            occurrences.append(i)

    if not occurrences:
        return {
            "file_path": file_path,
            "variable": variable,
            "target_line": target_line,
            "slice_lines": [],
            "slice_source": "",
            "total_lines": total_lines,
            "slice_size": 0,
            "reduction_pct": 100.0,
            "statements": [],
            "fallback": True,
        }

    slice_lines: set[int] = set()
    window = 10
    for occ in occurrences:
        start = max(1, occ - window)
        end = min(total_lines, occ + window)
        for ln in range(start, end + 1):
            slice_lines.add(ln)

    sorted_lines = sorted(slice_lines)
    slice_source = "\n".join(lines[ln - 1] for ln in sorted_lines)

    statements = []
    for ln in sorted_lines:
        code = lines[ln - 1]
        role = "use" if variable in code else "control_flow"
        statements.append({"line": ln, "code": code, "role": role})

    slice_size = len(sorted_lines)
    reduction_pct = round((1 - slice_size / total_lines) * 100, 2) if total_lines > 0 else 0.0

    return {
        "file_path": file_path,
        "variable": variable,
        "target_line": target_line,
        "slice_lines": sorted_lines,
        "slice_source": slice_source,
        "total_lines": total_lines,
        "slice_size": slice_size,
        "reduction_pct": reduction_pct,
        "statements": statements,
        "fallback": True,
    }


def backward_slice(file_path: str, variable: str, target_line: int) -> dict[str, Any]:
    """Compute the backward slice for a variable at a given line.

    Returns the minimal set of statements that influence the variable's value
    at target_line, using Weiser's algorithm approximated via AST analysis.
    """
    if not os.path.isfile(file_path):
        return {
            "file_path": file_path,
            "variable": variable,
            "target_line": target_line,
            "error": f"File not found: {file_path}",
            "slice_lines": [],
            "slice_source": "",
            "total_lines": 0,
            "slice_size": 0,
            "reduction_pct": 0.0,
            "statements": [],
        }

    try:
        with open(file_path, encoding="utf-8") as f:
            source = f.read()
    except UnicodeDecodeError:
        return {
            "file_path": file_path,
            "variable": variable,
            "target_line": target_line,
            "error": "Binary or non-UTF-8 file",
            "slice_lines": [],
            "slice_source": "",
            "total_lines": 0,
            "slice_size": 0,
            "reduction_pct": 0.0,
            "statements": [],
        }

    if not source.strip():
        return {
            "file_path": file_path,
            "variable": variable,
            "target_line": target_line,
            "slice_lines": [],
            "slice_source": "",
            "total_lines": 0,
            "slice_size": 0,
            "reduction_pct": 100.0,
            "statements": [],
        }

    lines = source.splitlines()
    total_lines = len(lines)

    try:
        tree = ast.parse(source, filename=file_path)
    except SyntaxError:
        return _text_based_fallback(source, file_path, variable, target_line)

    definitions, uses = _build_def_use_chains(tree)

    # BFS backward from target_line
    slice_lines: set[int] = set()
    slice_lines.add(target_line)

    # Seed the worklist with the target variable
    worklist: deque[str] = deque()
    worklist.append(variable)

    # Also include any other variables used at the target line
    target_uses = uses.get(target_line, set())
    for var in target_uses:
        if var not in worklist:
            worklist.append(var)

    visited_vars: set[str] = set()

    while worklist:
        var = worklist.popleft()
        if var in visited_vars:
            continue
        visited_vars.add(var)

        def_lines = definitions.get(var, [])
        for def_line in def_lines:
            if def_line > target_line:
                continue
            slice_lines.add(def_line)

            # Add variables used at this definition line to the worklist
            line_uses = uses.get(def_line, set())
            for used_var in line_uses:
                if used_var not in visited_vars:
                    worklist.append(used_var)

    # Add enclosing control flow for all slice lines
    control_lines: set[int] = set()
    for sl in list(slice_lines):
        for cl in _find_enclosing_control(tree, sl):
            control_lines.add(cl)

    # Control flow lines may themselves use variables we should trace
    for cl in control_lines:
        slice_lines.add(cl)
        cl_uses = uses.get(cl, set())
        for var in cl_uses:
            if var not in visited_vars:
                worklist.append(var)
                visited_vars.add(var)
                for def_line in definitions.get(var, []):
                    if def_line <= target_line:
                        slice_lines.add(def_line)

    sorted_lines = sorted(slice_lines)

    # Build the statements list with role annotations
    # Determine definitions set for role tagging
    all_def_lines: set[int] = set()
    for var in visited_vars:
        for dl in definitions.get(var, []):
            all_def_lines.add(dl)

    statements = []
    source_parts = []
    for ln in sorted_lines:
        if 1 <= ln <= total_lines:
            code = lines[ln - 1]
            source_parts.append(code)

            if ln in control_lines and ln not in all_def_lines:
                role = "control_flow"
            elif ln in all_def_lines:
                role = "definition"
            else:
                role = "use"
            statements.append({"line": ln, "code": code, "role": role})

    slice_source = "\n".join(source_parts)
    slice_size = len(sorted_lines)
    reduction_pct = round((1 - slice_size / total_lines) * 100, 2) if total_lines > 0 else 0.0

    return {
        "file_path": file_path,
        "variable": variable,
        "target_line": target_line,
        "slice_lines": sorted_lines,
        "slice_source": slice_source,
        "total_lines": total_lines,
        "slice_size": slice_size,
        "reduction_pct": reduction_pct,
        "statements": statements,
    }
