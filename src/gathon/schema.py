"""Unified schema bridging NodeInfo/EdgeInfo and gathon dict format."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class NodeKind(StrEnum):
    # code graph kinds
    FILE = "File"
    CLASS = "Class"
    FUNCTION = "Function"
    TEST = "Test"
    TYPE = "Type"
    # gathon extended kinds
    DOCUMENT = "Document"
    SECTION = "Section"
    SCHEMA = "Schema"
    CONCEPT = "Concept"
    IMAGE = "Image"
    VIDEO = "Video"
    ENDPOINT = "Endpoint"
    API_RESOURCE = "APIResource"
    CONFIG_FILE = "ConfigFile"
    CONFIG_KEY = "ConfigKey"


class EdgeKind(StrEnum):
    # code graph kinds
    CALLS = "CALLS"
    IMPORTS_FROM = "IMPORTS_FROM"
    INHERITS = "INHERITS"
    IMPLEMENTS = "IMPLEMENTS"
    CONTAINS = "CONTAINS"
    TESTED_BY = "TESTED_BY"
    DEPENDS_ON = "DEPENDS_ON"
    REFERENCES = "REFERENCES"
    # gathon extended kinds
    SEMANTICALLY_SIMILAR = "SEMANTICALLY_SIMILAR"
    CASE_OF = "CASE_OF"
    BELONGS_TO_DOMAIN = "BELONGS_TO_DOMAIN"
    METHOD_OF = "METHOD_OF"


class FileType(StrEnum):
    CODE = "code"
    DOCUMENT = "document"
    PAPER = "paper"
    IMAGE = "image"
    VIDEO = "video"
    CONFIG = "config"
    API_SPEC = "api_spec"


class Confidence(StrEnum):
    EXTRACTED = "EXTRACTED"
    INFERRED = "INFERRED"
    AMBIGUOUS = "AMBIGUOUS"


CONFIDENCE_SCORES: dict[str, float] = {
    "EXTRACTED": 1.0,
    "INFERRED": 0.5,
    "AMBIGUOUS": 0.2,
}


class Pipeline(StrEnum):
    CODE_GRAPH = "code_graph"
    GATHON_DOC = "gathon_doc"
    GATHON_PDF = "gathon_pdf"
    GATHON_OFFICE = "gathon_office"
    GATHON_IMAGE = "gathon_image"
    GATHON_VIDEO = "gathon_video"
    OPENAPI_YAML = "openapi_yaml"
    CONFIG_YAML = "config_yaml"
    GATHON_URL = "gathon_url"


@dataclass
class UnifiedNode:
    kind: str
    name: str
    qualified_name: str
    file_path: str
    line_start: int = 0
    line_end: int = 0
    language: str = ""
    parent_name: str | None = None
    params: str | None = None
    return_type: str | None = None
    modifiers: str | None = None
    is_test: bool = False
    extra: dict = field(default_factory=dict)
    # gathon extensions
    label: str = ""
    file_type: str = FileType.CODE
    source_url: str = ""
    source_location: str = ""
    confidence: str = Confidence.EXTRACTED
    confidence_score: float = 1.0
    pipeline: str = ""
    captured_at: str = ""
    author: str = ""

    def __post_init__(self) -> None:
        if not self.label:
            self.label = self.name


@dataclass
class UnifiedEdge:
    kind: str
    source_qualified: str
    target_qualified: str
    file_path: str
    line: int = 0
    extra: dict = field(default_factory=dict)
    confidence: float = 1.0
    confidence_tier: str = Confidence.EXTRACTED
    # gathon extensions
    relation: str = ""
    weight: float = 1.0

    def __post_init__(self) -> None:
        if not self.relation:
            self.relation = self.kind.lower()
