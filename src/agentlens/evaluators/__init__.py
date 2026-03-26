"""Pluggable evaluators for trajectory analysis."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from agentlens.models.evaluation import EvalLevel, EvalResult
from agentlens.models.expectation import TaskExpectation
from agentlens.models.trace import Trace

if TYPE_CHECKING:
    pass


class Evaluator(Protocol):
    """Protocol for all evaluators."""

    name: str
    level: EvalLevel

    def evaluate(self, trace: Trace, expected: TaskExpectation | None = None) -> list[EvalResult]:
        """Evaluate a trace and return results."""
        ...


def default_evaluators() -> list[Evaluator]:
    """Return all default evaluators."""
    from agentlens.evaluators.behavior import (
        LoopDetector,
        RecoveryEvaluator,
        StepEfficiencyEvaluator,
        ToolSelectionEvaluator,
    )
    from agentlens.evaluators.business import HumanHandoffEvaluator, TaskCompletionEvaluator
    from agentlens.evaluators.operational import CostEvaluator, LatencyEvaluator, VarianceEvaluator
    from agentlens.evaluators.risk import (
        HallucinationFlagEvaluator,
        PolicyViolationEvaluator,
        UnauthorizedActionDetector,
    )

    return [
        TaskCompletionEvaluator(),
        HumanHandoffEvaluator(),
        ToolSelectionEvaluator(),
        StepEfficiencyEvaluator(),
        LoopDetector(),
        RecoveryEvaluator(),
        UnauthorizedActionDetector(),
        HallucinationFlagEvaluator(),
        PolicyViolationEvaluator(),
        LatencyEvaluator(),
        CostEvaluator(),
        VarianceEvaluator(),
    ]


__all__ = ["Evaluator", "default_evaluators"]
