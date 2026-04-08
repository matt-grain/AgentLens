"""Pluggable evaluators for trajectory analysis."""

from __future__ import annotations

from typing import Protocol

from agentlens.models.evaluation import EvalLevel, EvalResult
from agentlens.models.expectation import TaskExpectation
from agentlens.models.trace import Trace


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
    from agentlens.evaluators.rag import ContextGroundingEvaluator, RetrievalRelevanceEvaluator
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
        # RAG
        RetrievalRelevanceEvaluator(),
        ContextGroundingEvaluator(),
    ]


def guard_evaluators() -> list[Evaluator]:
    """Return evaluators suitable for real-time guard checks (risk + behavior)."""
    from agentlens.evaluators.behavior import LoopDetector
    from agentlens.evaluators.risk import (
        HallucinationFlagEvaluator,
        PolicyViolationEvaluator,
        UnauthorizedActionDetector,
    )

    return [
        HallucinationFlagEvaluator(),
        PolicyViolationEvaluator(),
        UnauthorizedActionDetector(),
        LoopDetector(),
    ]


__all__ = ["Evaluator", "default_evaluators", "guard_evaluators"]
