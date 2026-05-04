"""Tree-sitter based file parsing with regex fallback for Python."""

from __future__ import annotations

import os
import re
from pathlib import Path

from .models import (
    FileSymbols,
    ImportInfo,
    SymbolInfo,
    compute_body_hash,
)
from .queries import LANGUAGE_QUERIES

EXTENSION_MAP = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".java": "java",
}

try:
    from tree_sitter_languages import get_language, get_parser

    _HAS_TREE_SITTER = True
except ImportError:
    _HAS_TREE_SITTER = False


def detect_language(file_path: str) -> str | None:
    ext = Path(file_path).suffix.lower()
    return EXTENSION_MAP.get(ext)


def parse_file(file_path: str, language: str | None = None) -> FileSymbols:
    """Parse a file and extract symbols, imports, and dependencies."""
    if language is None:
        language = detect_language(file_path)
    if language is None:
        return FileSymbols(file_path=file_path, language="unknown", mtime=_get_mtime(file_path))

    mtime = _get_mtime(file_path)

    if _HAS_TREE_SITTER and language in LANGUAGE_QUERIES:
        return _parse_with_tree_sitter(file_path, language, mtime)

    if language == "python":
        return _parse_python_regex(file_path, mtime)

    return FileSymbols(file_path=file_path, language=language, mtime=mtime)


def _get_mtime(file_path: str) -> float:
    try:
        return os.path.getmtime(file_path)
    except OSError:
        return 0.0


def _read_file(file_path: str) -> str:
    with open(file_path, encoding="utf-8", errors="replace") as f:
        return f.read()


def _read_lines(file_path: str) -> list[str]:
    with open(file_path, encoding="utf-8", errors="replace") as f:
        return f.readlines()


def _module_name_from_path(file_path: str) -> str:
    p = Path(file_path)
    stem = p.stem if p.stem != "__init__" else p.parent.name
    return stem


def _is_test_symbol(name: str, file_path: str) -> bool:
    if name.startswith("test_") or name.startswith("Test"):
        return True
    base = Path(file_path).stem
    return base.startswith("test_") or base.endswith("_test")


# ---------------------------------------------------------------------------
# Tree-sitter parser
# ---------------------------------------------------------------------------

def _parse_with_tree_sitter(file_path: str, language: str, mtime: float) -> FileSymbols:
    source = _read_file(file_path)
    source_bytes = source.encode("utf-8")

    parser = get_parser(language)
    tree = parser.parse(source_bytes)
    root = tree.root_node

    lang_obj = get_language(language)
    queries = LANGUAGE_QUERIES.get(language, {})
    module = _module_name_from_path(file_path)

    symbols: list[SymbolInfo] = []
    imports: list[ImportInfo] = []

    # Build a class map: node_id -> class_name for parent resolution
    class_map: dict[int, str] = {}

    # --- Extract classes ---
    class_query_str = queries.get("classes") or queries.get("types")
    if class_query_str:
        _extract_classes(
            lang_obj, class_query_str, root, source_bytes, source,
            file_path, language, module, symbols, class_map,
        )

    # --- Extract functions/methods ---
    func_query_str = queries.get("functions")
    if func_query_str:
        _extract_functions(
            lang_obj, func_query_str, root, source_bytes, source,
            file_path, language, module, symbols, class_map,
        )

    # --- Extract imports ---
    import_queries = queries.get("imports", [])
    if isinstance(import_queries, str):
        import_queries = [import_queries]
    for iq in import_queries:
        _extract_imports(lang_obj, iq, root, source_bytes, source, language, imports)

    # --- Extract module-level assignments (Python) ---
    assign_query_str = queries.get("assignments")
    if assign_query_str and language == "python":
        _extract_python_assignments(
            lang_obj, assign_query_str, root, source_bytes, source,
            file_path, language, module, symbols,
        )

    # --- Traits (Rust) ---
    trait_query_str = queries.get("traits")
    if trait_query_str:
        _extract_classes(
            lang_obj, trait_query_str, root, source_bytes, source,
            file_path, language, module, symbols, class_map, kind_override="class",
        )

    # --- Interfaces/type aliases (TypeScript) ---
    iface_query_str = queries.get("interfaces")
    if iface_query_str:
        _extract_classes(
            lang_obj, iface_query_str, root, source_bytes, source,
            file_path, language, module, symbols, class_map, kind_override="class",
        )

    talias_query_str = queries.get("type_aliases")
    if talias_query_str:
        _extract_classes(
            lang_obj, talias_query_str, root, source_bytes, source,
            file_path, language, module, symbols, class_map, kind_override="variable",
        )

    return FileSymbols(
        file_path=file_path,
        language=language,
        symbols=symbols,
        imports=imports,
        mtime=mtime,
    )


def _node_text(node, source_bytes: bytes) -> str:
    return source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _get_body_text(node, source: str) -> str:
    lines = source.splitlines()
    start = node.start_point[0]
    end = node.end_point[0]
    return "\n".join(lines[start:end + 1])


def _find_parent_class(node, class_map: dict[int, str]) -> str:
    """Walk up the tree to find if this node is inside a class."""
    current = node.parent
    while current is not None:
        if current.id in class_map:
            return class_map[current.id]
        current = current.parent
    return ""


def _is_module_level(node) -> bool:
    """Check if a node is at module level (parent is module/program)."""
    parent = node.parent
    module_types = ("module", "program", "source_file", "translation_unit")
    return parent is not None and parent.type in module_types


def _extract_python_decorators(node, source_bytes: bytes) -> list[str]:
    decorators = []
    # In Python tree-sitter, decorators are sibling nodes before the function
    # or they're inside a decorated_definition parent
    parent = node.parent
    if parent and parent.type == "decorated_definition":
        for child in parent.children:
            if child.type == "decorator":
                dec_text = _node_text(child, source_bytes).lstrip("@").strip()
                decorators.append(dec_text)
    return decorators


def _extract_python_params(node, source_bytes: bytes) -> list[str]:
    params = []
    for child in node.children:
        if child.type == "parameters":
            for param in child.children:
                if param.type in ("identifier", "typed_parameter", "default_parameter",
                                  "typed_default_parameter", "list_splat_pattern",
                                  "dictionary_splat_pattern"):
                    text = _node_text(param, source_bytes)
                    if text not in ("(", ")", ",", "self", "cls"):
                        params.append(text)
    return params


def _extract_python_return_type(node, source_bytes: bytes) -> str:
    for child in node.children:
        if child.type == "type":
            return _node_text(child, source_bytes)
    # look for return_type annotation
    for child in node.children:
        if child.type == "->":
            idx = list(node.children).index(child)
            if idx + 1 < len(node.children):
                return _node_text(node.children[idx + 1], source_bytes)
    return ""


def _extract_docstring(node, source_bytes: bytes, language: str) -> str:
    """Extract docstring from a function or class body."""
    body = None
    for child in node.children:
        if child.type in ("block", "body", "class_body"):
            body = child
            break
    if body is None:
        return ""

    for child in body.children:
        if child.type == "expression_statement":
            for sub in child.children:
                if sub.type == "string":
                    raw = _node_text(sub, source_bytes)
                    return raw.strip("\"'").strip()
        elif child.type in ("comment", "string"):
            raw = _node_text(child, source_bytes)
            return raw.strip("\"'").strip()
        elif child.type not in ("newline", "indent", "dedent", "NEWLINE", "INDENT", "DEDENT"):
            break
    return ""


def _extract_signature(node, source_bytes: bytes, language: str) -> str:
    """Build a one-line signature from the node."""
    if language == "python":
        parts = []
        for child in node.children:
            if child.type == "block":
                break
            parts.append(_node_text(child, source_bytes))
        sig = " ".join(parts).strip()
        if sig and not sig.endswith(":"):
            sig += ":"
        return sig

    # For other languages, take everything up to the body
    parts = []
    for child in node.children:
        if child.type in ("block", "statement_block", "class_body",
                          "declaration_list", "field_declaration_list",
                          "body", "compound_statement"):
            break
        parts.append(_node_text(child, source_bytes))
    return " ".join(parts).strip()


def _extract_classes(
    lang_obj, query_str: str, root, source_bytes: bytes, source: str,
    file_path: str, language: str, module: str,
    symbols: list[SymbolInfo], class_map: dict[int, str],
    kind_override: str | None = None,
):
    query = lang_obj.query(query_str)
    captures = query.captures(root)

    # Group captures by their associated node
    node_names: dict[int, tuple] = {}  # node_id -> (node, name)
    for cap_node, cap_name in captures:
        if cap_name == "name":
            # find the parent capture
            pass
        elif cap_name in ("cls", "typ", "iface", "talias", "trait", "mod"):
            node_names[cap_node.id] = (cap_node, None)

    # Second pass: match names to their parent nodes
    for cap_node, cap_name in captures:
        if cap_name == "name":
            parent = cap_node.parent
            while parent:
                if parent.id in node_names:
                    entry = node_names[parent.id]
                    node_names[parent.id] = (entry[0], _node_text(cap_node, source_bytes))
                    break
                parent = parent.parent

    for node_id, (node, name) in node_names.items():
        if name is None:
            continue

        class_map[node_id] = name
        kind = kind_override or "class"
        qualified = f"{module}.{name}"
        body_text = _get_body_text(node, source)
        sig = _extract_signature(node, source_bytes, language)
        docstring = _extract_docstring(node, source_bytes, language)

        # Extract base classes (Python)
        bases: list[str] = []
        if language == "python":
            for child in node.children:
                if child.type == "argument_list":
                    for arg in child.children:
                        if arg.type not in ("(", ")", ","):
                            bases.append(_node_text(arg, source_bytes))

        symbols.append(SymbolInfo(
            name=name,
            qualified_name=qualified,
            kind=kind,
            file_path=file_path,
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            language=language,
            signature=sig,
            params=bases,
            return_type="",
            decorators=(
                _extract_python_decorators(node, source_bytes)
                if language == "python" else []
            ),
            docstring=docstring,
            parent_name="",
            body_hash=compute_body_hash(body_text),
            is_test=_is_test_symbol(name, file_path),
        ))


def _extract_functions(
    lang_obj, query_str: str, root, source_bytes: bytes, source: str,
    file_path: str, language: str, module: str,
    symbols: list[SymbolInfo], class_map: dict[int, str],
):
    query = lang_obj.query(query_str)
    captures = query.captures(root)

    node_names: dict[int, tuple] = {}
    for cap_node, cap_name in captures:
        if cap_name == "func":
            node_names[cap_node.id] = (cap_node, None)

    for cap_node, cap_name in captures:
        if cap_name == "name":
            parent = cap_node.parent
            while parent:
                if parent.id in node_names:
                    entry = node_names[parent.id]
                    if entry[1] is None:
                        node_names[parent.id] = (entry[0], _node_text(cap_node, source_bytes))
                    break
                parent = parent.parent

    for node_id, (node, name) in node_names.items():
        if name is None:
            # Arrow functions without names
            continue

        parent_class = _find_parent_class(node, class_map)
        kind = "method" if parent_class else "function"
        if parent_class:
            qualified = f"{module}.{parent_class}.{name}"
        else:
            qualified = f"{module}.{name}"

        body_text = _get_body_text(node, source)
        sig = _extract_signature(node, source_bytes, language)
        docstring = _extract_docstring(node, source_bytes, language)

        params: list[str] = []
        return_type = ""
        decorators: list[str] = []

        if language == "python":
            params = _extract_python_params(node, source_bytes)
            return_type = _extract_python_return_type(node, source_bytes)
            decorators = _extract_python_decorators(node, source_bytes)
        else:
            # Generic param extraction: look for formal_parameters / parameter_list
            for child in node.children:
                if child.type in ("formal_parameters", "parameters", "parameter_list"):
                    for param in child.children:
                        if param.type not in ("(", ")", ",", "{", "}"):
                            params.append(_node_text(param, source_bytes))

        symbols.append(SymbolInfo(
            name=name,
            qualified_name=qualified,
            kind=kind,
            file_path=file_path,
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            language=language,
            signature=sig,
            params=params,
            return_type=return_type,
            decorators=decorators,
            docstring=docstring,
            parent_name=parent_class,
            body_hash=compute_body_hash(body_text),
            is_test=_is_test_symbol(name, file_path),
        ))


def _extract_imports(
    lang_obj, query_str: str, root, source_bytes: bytes, source: str,
    language: str, imports: list[ImportInfo],
):
    query = lang_obj.query(query_str)
    captures = query.captures(root)

    for cap_node, cap_name in captures:
        if cap_name != "imp":
            continue

        text = _node_text(cap_node, source_bytes)
        line = cap_node.start_point[0] + 1

        if language == "python":
            _parse_python_import_node(cap_node, source_bytes, line, imports)
        elif language in ("javascript", "typescript"):
            _parse_js_import_node(text, line, imports)
        elif language == "go":
            _parse_go_import_node(cap_node, source_bytes, line, imports)
        elif language == "rust":
            _parse_rust_import_node(text, line, imports)
        elif language == "java":
            _parse_java_import_node(text, line, imports)


def _parse_python_import_node(node, source_bytes: bytes, line: int, imports: list[ImportInfo]):
    if node.type == "import_from_statement":
        module_name = ""
        names = []
        for child in node.children:
            if child.type == "dotted_name":
                if not module_name:
                    module_name = _node_text(child, source_bytes)
                else:
                    names.append(_node_text(child, source_bytes))
            elif child.type == "aliased_import":
                name_node = child.children[0] if child.children else None
                if name_node:
                    names.append(_node_text(name_node, source_bytes))
            elif child.type == "identifier":
                names.append(_node_text(child, source_bytes))
            elif child.type == "relative_import":
                module_name = _node_text(child, source_bytes)
        imports.append(ImportInfo(module=module_name, names=names, line=line, is_from=True))
    elif node.type == "import_statement":
        for child in node.children:
            if child.type == "dotted_name":
                imports.append(ImportInfo(
                    module=_node_text(child, source_bytes),
                    names=[],
                    line=line,
                    is_from=False,
                ))
            elif child.type == "aliased_import":
                name_node = child.children[0] if child.children else None
                if name_node:
                    imports.append(ImportInfo(
                        module=_node_text(name_node, source_bytes),
                        names=[],
                        line=line,
                        is_from=False,
                    ))


def _parse_js_import_node(text: str, line: int, imports: list[ImportInfo]):
    # import { a, b } from "module"
    # import x from "module"
    m = re.search(r"""from\s+["']([^"']+)["']""", text)
    if m:
        module = m.group(1)
        names_match = re.search(r"\{([^}]+)\}", text)
        names = []
        if names_match:
            for n in names_match.group(1).split(","):
                n = n.strip().split(" as ")[0].strip()
                if n:
                    names.append(n)
        else:
            default_match = re.match(r"import\s+(\w+)", text)
            if default_match:
                names = [default_match.group(1)]
        imports.append(ImportInfo(module=module, names=names, line=line, is_from=True))
    else:
        m2 = re.search(r"""import\s+["']([^"']+)["']""", text)
        if m2:
            imports.append(ImportInfo(module=m2.group(1), names=[], line=line, is_from=False))


def _parse_go_import_node(node, source_bytes: bytes, line: int, imports: list[ImportInfo]):
    for child in node.children:
        if child.type == "import_spec_list":
            for spec in child.children:
                if spec.type == "import_spec":
                    text = _node_text(spec, source_bytes).strip().strip('"')
                    if text:
                        imports.append(ImportInfo(
                            module=text, names=[],
                            line=spec.start_point[0] + 1,
                            is_from=False,
                        ))
        elif child.type == "import_spec":
            text = _node_text(child, source_bytes).strip().strip('"')
            if text:
                imports.append(ImportInfo(module=text, names=[], line=line, is_from=False))


def _parse_rust_import_node(text: str, line: int, imports: list[ImportInfo]):
    # use std::collections::HashMap;
    m = re.match(r"use\s+(.+);", text.strip())
    if m:
        path = m.group(1).strip()
        # handle {A, B} braces
        brace_match = re.search(r"\{([^}]+)\}", path)
        if brace_match:
            base = path[:brace_match.start()].rstrip("::")
            names = [n.strip() for n in brace_match.group(1).split(",") if n.strip()]
            imports.append(ImportInfo(module=base, names=names, line=line, is_from=True))
        else:
            parts = path.split("::")
            if len(parts) > 1:
                imports.append(ImportInfo(
                    module="::".join(parts[:-1]),
                    names=[parts[-1]], line=line, is_from=True,
                ))
            else:
                imports.append(ImportInfo(module=path, names=[], line=line, is_from=False))


def _parse_java_import_node(text: str, line: int, imports: list[ImportInfo]):
    m = re.match(r"import\s+(static\s+)?(.+);", text.strip())
    if m:
        path = m.group(2).strip()
        parts = path.rsplit(".", 1)
        if len(parts) == 2:
            imports.append(ImportInfo(module=parts[0], names=[parts[1]], line=line, is_from=True))
        else:
            imports.append(ImportInfo(module=path, names=[], line=line, is_from=False))


def _extract_python_assignments(
    lang_obj, query_str: str, root, source_bytes: bytes, source: str,
    file_path: str, language: str, module: str,
    symbols: list[SymbolInfo],
):
    query = lang_obj.query(query_str)
    captures = query.captures(root)

    node_names: dict[int, tuple] = {}
    for cap_node, cap_name in captures:
        if cap_name == "assign":
            node_names[cap_node.id] = (cap_node, None)
        elif cap_name == "name":
            parent = cap_node.parent
            while parent:
                if parent.id in node_names:
                    entry = node_names[parent.id]
                    if entry[1] is None:
                        node_names[parent.id] = (entry[0], _node_text(cap_node, source_bytes))
                    break
                parent = parent.parent

    for node_id, (node, name) in node_names.items():
        if name is None or name.startswith("_"):
            continue
        if not _is_module_level(node):
            continue

        text = _node_text(node, source_bytes)
        symbols.append(SymbolInfo(
            name=name,
            qualified_name=f"{module}.{name}",
            kind="variable",
            file_path=file_path,
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            language=language,
            signature=text.split("\n")[0],
            body_hash=compute_body_hash(text),
            is_test=False,
        ))


# ---------------------------------------------------------------------------
# Regex fallback parser (Python only)
# ---------------------------------------------------------------------------

_RE_FUNC = re.compile(
    r"^(?P<indent>[ \t]*)(?P<decorators>(?:@\w[\w.]*(?:\([^)]*\))?\s*\n(?:[ \t]*))*)?"
    r"(?:async\s+)?def\s+(?P<name>\w+)\s*\((?P<params>[^)]*)\)"
    r"(?:\s*->\s*(?P<return>[^:]+))?\s*:",
    re.MULTILINE,
)

_RE_CLASS = re.compile(
    r"^(?P<indent>[ \t]*)class\s+(?P<name>\w+)\s*(?:\((?P<bases>[^)]*)\))?\s*:",
    re.MULTILINE,
)

_RE_IMPORT = re.compile(
    r"^(?:from\s+(?P<from_mod>[\w.]+)\s+import\s+(?P<from_names>[^#\n]+(?:\([^)]*\))?)"
    r"|import\s+(?P<mod>[\w.]+))",
    re.MULTILINE,
)

_RE_ASSIGN = re.compile(
    r"^(?P<name>[A-Z][A-Z_0-9]*)\s*=",
    re.MULTILINE,
)


def _parse_python_regex(file_path: str, mtime: float = 0.0) -> FileSymbols:
    source = _read_file(file_path)
    lines = source.splitlines()
    module = _module_name_from_path(file_path)

    symbols: list[SymbolInfo] = []
    imports: list[ImportInfo] = []

    # Track classes for method resolution
    class_ranges: list[tuple[str, int, int, int]] = []  # (name, indent_len, start, end)

    # Extract classes
    for m in _RE_CLASS.finditer(source):
        name = m.group("name")
        indent_len = len(m.group("indent") or "")
        start_line = source[:m.start()].count("\n") + 1
        end_line = _find_block_end(lines, start_line - 1, indent_len)
        class_ranges.append((name, indent_len, start_line, end_line))

        bases_str = m.group("bases") or ""
        bases = [b.strip() for b in bases_str.split(",") if b.strip()] if bases_str else []

        body = "\n".join(lines[start_line - 1:end_line])
        docstring = _extract_regex_docstring(lines, start_line)

        symbols.append(SymbolInfo(
            name=name,
            qualified_name=f"{module}.{name}",
            kind="class",
            file_path=file_path,
            line_start=start_line,
            line_end=end_line,
            language="python",
            signature=f"class {name}({bases_str}):" if bases_str else f"class {name}:",
            params=bases,
            docstring=docstring,
            body_hash=compute_body_hash(body),
            is_test=_is_test_symbol(name, file_path),
        ))

    # Extract functions/methods
    for m in _RE_FUNC.finditer(source):
        name = m.group("name")
        indent_len = len(m.group("indent") or "")
        start_line = source[:m.start()].count("\n") + 1
        # Adjust for decorators
        dec_text = m.group("decorators") or ""
        if dec_text:
            dec_lines = dec_text.strip().count("\n")
            start_line -= dec_lines

        end_line = _find_block_end(lines, source[:m.end()].count("\n"), indent_len)
        params_str = m.group("params") or ""
        params = [
            p.strip() for p in params_str.split(",")
            if p.strip() and p.strip() not in ("self", "cls")
        ]
        return_type = (m.group("return") or "").strip()

        decorators = []
        if dec_text:
            for dec_line in dec_text.strip().splitlines():
                d = dec_line.strip().lstrip("@")
                if d:
                    decorators.append(d)

        parent_class = ""
        kind = "function"
        for cname, cindent, cstart, cend in class_ranges:
            if indent_len > cindent and start_line >= cstart and end_line <= cend:
                parent_class = cname
                kind = "method"
                break

        qualified = f"{module}.{parent_class}.{name}" if parent_class else f"{module}.{name}"
        body = "\n".join(lines[start_line - 1:end_line])
        docstring = _extract_regex_docstring(lines, source[:m.end()].count("\n"))

        sig_line = m.group(0).split("\n")[-1].strip()
        if dec_text:
            sig_line = m.group(0).split("\n")[-1].strip()

        symbols.append(SymbolInfo(
            name=name,
            qualified_name=qualified,
            kind=kind,
            file_path=file_path,
            line_start=start_line,
            line_end=end_line,
            language="python",
            signature=sig_line,
            params=params,
            return_type=return_type,
            decorators=decorators,
            docstring=docstring,
            parent_name=parent_class,
            body_hash=compute_body_hash(body),
            is_test=_is_test_symbol(name, file_path),
        ))

    # Extract imports
    for m in _RE_IMPORT.finditer(source):
        line_num = source[:m.start()].count("\n") + 1
        if m.group("from_mod"):
            mod = m.group("from_mod")
            names_str = m.group("from_names")
            # Handle multi-line imports: if we see '(' without ')', read ahead
            if "(" in names_str and ")" not in names_str:
                end_pos = source.find(")", m.end())
                if end_pos != -1:
                    names_str = source[m.start("from_names"):end_pos + 1]
            # Strip parens, split, clean
            names_str = names_str.strip("() \n")
            names = [
                n.strip().split(" as ")[0].strip()
                for n in names_str.replace("\n", ",").split(",")
                if n.strip() and n.strip() not in ("(", ")", "\\")
            ]
            imports.append(ImportInfo(module=mod, names=names, line=line_num, is_from=True))
        else:
            imports.append(ImportInfo(
                module=m.group("mod"), names=[],
                line=line_num, is_from=False,
            ))

    # Extract module-level constants
    for m in _RE_ASSIGN.finditer(source):
        line_num = source[:m.start()].count("\n") + 1
        name = m.group("name")
        # Only module level (no indent before)
        col = m.start() - source.rfind("\n", 0, m.start()) - 1
        if col == 0:
            full_line = lines[line_num - 1] if line_num <= len(lines) else ""
            symbols.append(SymbolInfo(
                name=name,
                qualified_name=f"{module}.{name}",
                kind="variable",
                file_path=file_path,
                line_start=line_num,
                line_end=line_num,
                language="python",
                signature=full_line.strip(),
                body_hash=compute_body_hash(full_line),
                is_test=False,
            ))

    return FileSymbols(
        file_path=file_path,
        language="python",
        symbols=symbols,
        imports=imports,
        mtime=mtime,
    )


def _find_block_end(lines: list[str], start_idx: int, base_indent: int) -> int:
    """Find the last line of a Python block starting at start_idx."""
    end = start_idx + 1
    while end < len(lines):
        line = lines[end]
        stripped = line.strip()
        if not stripped:
            end += 1
            continue
        current_indent = len(line) - len(line.lstrip())
        if current_indent <= base_indent:
            break
        end += 1
    return end


def _extract_regex_docstring(lines: list[str], def_line_idx: int) -> str:
    """Extract docstring from lines following a def/class line."""
    idx = def_line_idx
    if idx >= len(lines):
        return ""
    # Look at the next non-empty line
    idx += 1
    while idx < len(lines) and not lines[idx].strip():
        idx += 1
    if idx >= len(lines):
        return ""
    line = lines[idx].strip()
    if line.startswith('"""') or line.startswith("'''"):
        quote = line[:3]
        if line.endswith(quote) and len(line) > 6:
            return line[3:-3].strip()
        # multiline docstring
        parts = [line[3:]]
        idx += 1
        while idx < len(lines):
            ln = lines[idx]
            if quote in ln:
                parts.append(ln.strip().rstrip(quote))
                break
            parts.append(ln.strip())
            idx += 1
        return "\n".join(parts).strip()
    return ""
