"""CTP — Python CLI output filter engine."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FilterResult:
    """Result of running a command through the filter engine."""

    output: str
    exit_code: int
    filter_name: str
    before_tokens: int
    after_tokens: int
    cache_hit: bool = False

    @property
    def savings_pct(self) -> float:
        if self.before_tokens == 0:
            return 0.0
        return (self.before_tokens - self.after_tokens) / self.before_tokens * 100
