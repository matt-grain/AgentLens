from __future__ import annotations

from datetime import datetime
from enum import StrEnum, unique
from typing import Any

from pydantic import BaseModel, Field


@unique
class EvalLevel(StrEnum):
    BUSINESS = "business"
    BEHAVIOR = "behavior"
    RISK = "risk"
    OPERATIONAL = "operational"


@unique
class EvalSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class EvalResult(BaseModel, frozen=True):
    evaluator_name: str
    level: EvalLevel
    score: float
    passed: bool
    message: str
    severity: EvalSeverity
    evidence: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class EvalSummary(BaseModel):
    """Aggregated evaluation results for a single trace."""

    trace_id: str
    task: str
    results: list[EvalResult]
    level_scores: dict[EvalLevel, float]
    overall_score: float
    timestamp: datetime

    @property
    def passed(self) -> bool:
        return all(r.passed for r in self.results)

    @property
    def critical_failures(self) -> list[EvalResult]:
        return [r for r in self.results if r.severity == EvalSeverity.CRITICAL and not r.passed]
