"""Benchmark suite — load and run evaluation over multiple trace files."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, computed_field

from agentlens.engine import EvaluationSuite
from agentlens.models.evaluation import EvalLevel, EvalSummary
from agentlens.models.expectation import TaskExpectation
from agentlens.models.trace import Trace

_PASS_THRESHOLD: float = 0.7


class BenchmarkCase(BaseModel, frozen=True):
    trace: str
    expectations: TaskExpectation | None = None


class BenchmarkSuite(BaseModel, frozen=True):
    name: str
    description: str = ""
    cases: list[BenchmarkCase]


class BenchmarkResult(BaseModel):
    suite_name: str
    total_cases: int
    passed: int
    failed: int
    average_score: float
    level_averages: dict[EvalLevel, float]
    case_results: list[EvalSummary]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def pass_rate(self) -> float:
        if self.total_cases == 0:
            return 0.0
        return self.passed / self.total_cases


def _aggregate_level_averages(summaries: list[EvalSummary]) -> dict[EvalLevel, float]:
    buckets: dict[EvalLevel, list[float]] = {level: [] for level in EvalLevel}
    for summary in summaries:
        for level, score in summary.level_scores.items():
            buckets[level].append(score)
    return {level: sum(scores) / len(scores) for level, scores in buckets.items() if scores}


def run_benchmark(suite_path: Path) -> BenchmarkResult:
    """Load a benchmark suite JSON and evaluate each case, returning aggregate results."""
    suite = BenchmarkSuite.model_validate_json(suite_path.read_text())
    engine = EvaluationSuite()
    summaries: list[EvalSummary] = []

    for case in suite.cases:
        trace_path = Path(case.trace)
        if not trace_path.exists():
            raise FileNotFoundError(f"Trace file not found: {trace_path}")
        trace = Trace.model_validate_json(trace_path.read_text())
        summary = engine.evaluate(trace, case.expectations)
        summaries.append(summary)

    passed = sum(1 for s in summaries if s.overall_score >= _PASS_THRESHOLD)
    average_score = sum(s.overall_score for s in summaries) / len(summaries) if summaries else 0.0

    return BenchmarkResult(
        suite_name=suite.name,
        total_cases=len(summaries),
        passed=passed,
        failed=len(summaries) - passed,
        average_score=average_score,
        level_averages=_aggregate_level_averages(summaries),
        case_results=summaries,
    )
