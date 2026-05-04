"""Tree-sitter query strings for each supported language."""

PYTHON_QUERIES = {
    "functions": "(function_definition name: (identifier) @name) @func",
    "classes": "(class_definition name: (identifier) @name) @cls",
    "imports": [
        "(import_statement) @imp",
        "(import_from_statement) @imp",
    ],
    "decorators": "(decorator) @dec",
    "assignments": "(assignment left: (identifier) @name) @assign",
}

JAVASCRIPT_QUERIES = {
    "functions": """[
        (function_declaration name: (identifier) @name) @func
        (arrow_function) @func
        (method_definition name: (property_identifier) @name) @func
    ]""",
    "classes": "(class_declaration name: (identifier) @name) @cls",
    "imports": [
        "(import_statement) @imp",
    ],
    "assignments": """[
        (variable_declaration) @assign
        (lexical_declaration) @assign
    ]""",
}

TYPESCRIPT_QUERIES = {
    "functions": """[
        (function_declaration name: (identifier) @name) @func
        (arrow_function) @func
        (method_definition name: (property_identifier) @name) @func
    ]""",
    "classes": "(class_declaration name: (identifier) @name) @cls",
    "imports": [
        "(import_statement) @imp",
    ],
    "assignments": """[
        (variable_declaration) @assign
        (lexical_declaration) @assign
    ]""",
    "interfaces": "(interface_declaration name: (type_identifier) @name) @iface",
    "type_aliases": "(type_alias_declaration name: (type_identifier) @name) @talias",
}

GO_QUERIES = {
    "functions": """[
        (function_declaration name: (identifier) @name) @func
        (method_declaration name: (field_identifier) @name) @func
    ]""",
    "imports": [
        "(import_declaration) @imp",
    ],
    "types": "(type_declaration (type_spec name: (type_identifier) @name)) @typ",
}

RUST_QUERIES = {
    "functions": "(function_item name: (identifier) @name) @func",
    "classes": """[
        (struct_item name: (type_identifier) @name) @cls
        (enum_item name: (type_identifier) @name) @cls
    ]""",
    "imports": [
        "(use_declaration) @imp",
    ],
    "traits": "(trait_item name: (type_identifier) @name) @trait",
    "impls": "(impl_item) @impl_block",
}

RUBY_QUERIES = {
    "functions": "(method name: (identifier) @name) @func",
    "classes": "(class name: (constant) @name) @cls",
    "imports": [],
    "modules": "(module name: (constant) @name) @mod",
}

JAVA_QUERIES = {
    "functions": "(method_declaration name: (identifier) @name) @func",
    "classes": """[
        (class_declaration name: (identifier) @name) @cls
        (interface_declaration name: (identifier) @name) @cls
    ]""",
    "imports": [
        "(import_declaration) @imp",
    ],
}

LANGUAGE_QUERIES = {
    "python": PYTHON_QUERIES,
    "javascript": JAVASCRIPT_QUERIES,
    "typescript": TYPESCRIPT_QUERIES,
    "go": GO_QUERIES,
    "rust": RUST_QUERIES,
    "ruby": RUBY_QUERIES,
    "java": JAVA_QUERIES,
}
