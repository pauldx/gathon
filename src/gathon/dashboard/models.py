"""Dashboard data models — all dataclasses, no logic."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SignalResult:
    name: str
    weight: float
    score: float
    description: str
    recommendation: str = ""


@dataclass
class WasteFinding:
    waste_type: str
    severity: str  # "low" | "medium" | "high" | "critical"
    description: str
    monthly_waste_tokens: int
    recommendation: str
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class CoachPattern:
    label: str
    detail: str
    category: str  # "good" | "bad"


@dataclass
class OverviewData:
    total_savings_tokens: int = 0
    estimated_cost_usd: float = 0.0
    ctp_savings: int = 0
    graph_savings: int = 0
    multimodal_savings: int = 0
    memory_savings: int = 0
    session_event_count: int = 0
    days: int = 7
    trend: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class CtpTabData:
    total_commands: int = 0
    total_savings: int = 0
    avg_savings_pct: float = 0.0
    by_filter: list[dict[str, Any]] = field(default_factory=list)
    trend: list[dict[str, Any]] = field(default_factory=list)
    top_commands: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class CodeGraphTabData:
    unified_stats: dict[str, Any] = field(default_factory=dict)
    compression_summary: dict[str, Any] = field(default_factory=dict)
    by_tool: list[dict[str, Any]] = field(default_factory=list)
    pipeline_run_summary: dict[str, Any] = field(default_factory=dict)
    disclosure_stats: dict[str, Any] = field(default_factory=dict)
    trend: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class MultimodalTabData:
    nodes_by_pipeline: dict[str, int] = field(default_factory=dict)
    compression_by_pipeline: list[dict[str, Any]] = field(default_factory=list)
    pipeline_run_counts: dict[str, int] = field(default_factory=dict)
    total_multimodal_nodes: int = 0


@dataclass
class MemoryTabData:
    total: int = 0
    by_type: dict[str, int] = field(default_factory=dict)
    archived: int = 0
    avg_importance: float = 0.0
    archive_rate_pct: float = 0.0
    estimated_reuse_savings: int = 0
    roi_distribution: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class QualityTabData:
    score: float = 0.0
    grade: str = "F"
    band: str = "No Data"
    signals: list[SignalResult] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


@dataclass
class WasteTabData:
    findings: list[WasteFinding] = field(default_factory=list)
    severity_counts: dict[str, int] = field(default_factory=dict)


@dataclass
class CoachTabData:
    health_score: int = 0
    grade: str = "F"
    patterns_good: list[CoachPattern] = field(default_factory=list)
    patterns_bad: list[CoachPattern] = field(default_factory=list)
    snapshot: dict[str, Any] = field(default_factory=dict)


@dataclass
class DashboardData:
    generated_at: str = ""
    days: int = 7
    repo_path: str = ""
    overview: OverviewData = field(default_factory=OverviewData)
    ctp: CtpTabData = field(default_factory=CtpTabData)
    code_graph: CodeGraphTabData = field(default_factory=CodeGraphTabData)
    multimodal: MultimodalTabData = field(default_factory=MultimodalTabData)
    memory: MemoryTabData = field(default_factory=MemoryTabData)
    quality: QualityTabData = field(default_factory=QualityTabData)
    waste: WasteTabData = field(default_factory=WasteTabData)
    coach: CoachTabData = field(default_factory=CoachTabData)
