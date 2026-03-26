"""Operational-level evaluators for latency, cost, and variance."""

from __future__ import annotations

import math

from agentlens.models.evaluation import EvalLevel, EvalResult, EvalSeverity
from agentlens.models.expectation import TaskExpectation
from agentlens.models.trace import Trace

_INPUT_COST_PER_1K: float = 0.01
_OUTPUT_COST_PER_1K: float = 0.03


class LatencyEvaluator:
    """Evaluates total trace duration against latency thresholds."""

    name: str = "latency"
    level: EvalLevel = EvalLevel.OPERATIONAL

    def evaluate(self, trace: Trace, expected: TaskExpectation | None = None) -> list[EvalResult]:
        duration_s = trace.duration_ms / 1000.0
        score = self._score(duration_s)
        span_breakdown = {s.name: s.duration_ms for s in trace.spans}

        return [
            EvalResult(
                evaluator_name=self.name,
                level=self.level,
                score=score,
                passed=score >= 0.5,
                message=f"Total duration: {duration_s:.2f}s",
                severity=EvalSeverity.INFO if score >= 0.5 else EvalSeverity.WARNING,
                details={"duration_s": duration_s, "span_durations_ms": span_breakdown},
            )
        ]

    def _score(self, duration_s: float) -> float:
        if duration_s < 5:
            return 1.0
        if duration_s < 10:
            return 0.8
        if duration_s < 30:
            return 0.5
        return 0.3


class CostEvaluator:
    """Estimates LLM token cost and scores against cost thresholds."""

    name: str = "cost"
    level: EvalLevel = EvalLevel.OPERATIONAL

    def evaluate(self, trace: Trace, expected: TaskExpectation | None = None) -> list[EvalResult]:
        usage = trace.total_tokens
        if usage is None:
            return [
                EvalResult(
                    evaluator_name=self.name,
                    level=self.level,
                    score=1.0,
                    passed=True,
                    message="No token usage recorded.",
                    severity=EvalSeverity.INFO,
                )
            ]

        cost = (usage.input_tokens / 1000) * _INPUT_COST_PER_1K + (usage.output_tokens / 1000) * _OUTPUT_COST_PER_1K
        score = self._score(cost)

        return [
            EvalResult(
                evaluator_name=self.name,
                level=self.level,
                score=score,
                passed=score >= 0.5,
                message=f"Estimated cost: ${cost:.4f}",
                severity=EvalSeverity.INFO if score >= 0.5 else EvalSeverity.WARNING,
                details={
                    "estimated_cost_usd": round(cost, 6),
                    "input_tokens": usage.input_tokens,
                    "output_tokens": usage.output_tokens,
                },
            )
        ]

    def _score(self, cost: float) -> float:
        if cost < 0.01:
            return 1.0
        if cost < 0.05:
            return 0.8
        if cost < 0.10:
            return 0.5
        return 0.3


class VarianceEvaluator:
    """Measures consistency of span durations using coefficient of variation."""

    name: str = "variance"
    level: EvalLevel = EvalLevel.OPERATIONAL

    def evaluate(self, trace: Trace, expected: TaskExpectation | None = None) -> list[EvalResult]:
        durations = [s.duration_ms for s in trace.spans]

        if len(durations) < 2:
            return [
                EvalResult(
                    evaluator_name=self.name,
                    level=self.level,
                    score=1.0,
                    passed=True,
                    message="Insufficient spans to measure variance.",
                    severity=EvalSeverity.INFO,
                )
            ]

        cv = self._coefficient_of_variation(durations)
        score = self._score(cv)

        return [
            EvalResult(
                evaluator_name=self.name,
                level=self.level,
                score=score,
                passed=score >= 0.5,
                message=f"Duration CV: {cv:.2f}",
                severity=EvalSeverity.INFO if score >= 0.5 else EvalSeverity.WARNING,
                details={"coefficient_of_variation": round(cv, 4)},
            )
        ]

    def _coefficient_of_variation(self, durations: list[int]) -> float:
        n = len(durations)
        mean = sum(durations) / n
        if mean == 0:
            return 0.0
        variance = sum((d - mean) ** 2 for d in durations) / n
        return math.sqrt(variance) / mean

    def _score(self, cv: float) -> float:
        if cv < 0.5:
            return 1.0
        if cv < 1.0:
            return 0.7
        if cv < 2.0:
            return 0.5
        return 0.3
