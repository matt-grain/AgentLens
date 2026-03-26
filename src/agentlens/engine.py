"""Evaluation engine — orchestrates evaluators over a trace."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Final

from agentlens.evaluators import Evaluator, default_evaluators
from agentlens.models.evaluation import EvalLevel, EvalResult, EvalSummary
from agentlens.models.expectation import TaskExpectation
from agentlens.models.trace import Trace

_LEVEL_WEIGHTS: Final[dict[EvalLevel, float]] = {
    EvalLevel.BUSINESS: 0.30,
    EvalLevel.BEHAVIOR: 0.30,
    EvalLevel.RISK: 0.25,
    EvalLevel.OPERATIONAL: 0.15,
}


class EvaluationSuite:
    """Runs a configurable set of evaluators against a trace."""

    def __init__(self, evaluators: list[Evaluator] | None = None) -> None:
        self.evaluators: list[Evaluator] = evaluators if evaluators is not None else default_evaluators()

    def add_evaluator(self, evaluator: Evaluator) -> None:
        """Add a custom evaluator to the suite."""
        self.evaluators.append(evaluator)

    def remove_evaluator(self, name: str) -> None:
        """Remove an evaluator by name."""
        self.evaluators = [e for e in self.evaluators if e.name != name]

    def evaluate(self, trace: Trace, expected: TaskExpectation | None = None) -> EvalSummary:
        """Run all evaluators and return an aggregated summary."""
        results = [result for ev in self.evaluators for result in ev.evaluate(trace, expected)]
        level_scores = self._compute_level_scores(results)
        overall_score = self._compute_overall_score(level_scores)

        return EvalSummary(
            trace_id=trace.id,
            task=trace.task,
            results=results,
            level_scores=level_scores,
            overall_score=overall_score,
            timestamp=datetime.now(tz=UTC),
        )

    def _compute_level_scores(self, results: list[EvalResult]) -> dict[EvalLevel, float]:
        buckets: dict[EvalLevel, list[float]] = {level: [] for level in EvalLevel}
        for result in results:
            buckets[result.level].append(result.score)
        return {level: sum(scores) / len(scores) for level, scores in buckets.items() if scores}

    def _compute_overall_score(self, level_scores: dict[EvalLevel, float]) -> float:
        total_weight = sum(_LEVEL_WEIGHTS[level] for level in level_scores)
        if total_weight == 0:
            return 0.0
        weighted_sum = sum(level_scores[level] * _LEVEL_WEIGHTS[level] for level in level_scores)
        return weighted_sum / total_weight
