"""Tests for the EvaluationSuite engine."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from agentlens.engine import EvaluationSuite
from agentlens.models.evaluation import EvalLevel, EvalResult, EvalSeverity
from agentlens.models.expectation import TaskExpectation
from agentlens.models.trace import Span, SpanStatus, SpanType, TokenUsage, Trace

_BASE = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)


def _make_trace() -> Trace:
    span = Span(
        id="s1",
        span_type=SpanType.LLM_CALL,
        name="plan",
        input={"messages": []},
        output={"content": "done"},
        status=SpanStatus.SUCCESS,
        start_time=_BASE,
        end_time=_BASE + timedelta(milliseconds=500),
        token_usage=TokenUsage(input_tokens=50, output_tokens=25),
    )
    return Trace(
        id="trace001",
        task="test task",
        agent_name="test-agent",
        spans=[span],
        final_output="done",
        started_at=_BASE,
        completed_at=_BASE + timedelta(milliseconds=500),
    )


class _AlwaysPassEvaluator:
    name: str = "always_pass"
    level: EvalLevel = EvalLevel.BEHAVIOR

    def evaluate(self, trace: Trace, expected: TaskExpectation | None = None) -> list[EvalResult]:
        return [
            EvalResult(
                evaluator_name=self.name,
                level=self.level,
                score=1.0,
                passed=True,
                message="Always passes.",
                severity=EvalSeverity.INFO,
            )
        ]


class _AlwaysFailEvaluator:
    name: str = "always_fail"
    level: EvalLevel = EvalLevel.RISK

    def evaluate(self, trace: Trace, expected: TaskExpectation | None = None) -> list[EvalResult]:
        return [
            EvalResult(
                evaluator_name=self.name,
                level=self.level,
                score=0.0,
                passed=False,
                message="Always fails.",
                severity=EvalSeverity.CRITICAL,
            )
        ]


class TestEvaluationSuite:
    def test_evaluation_suite_runs_all_evaluators(self) -> None:
        # Arrange
        suite = EvaluationSuite(evaluators=[_AlwaysPassEvaluator(), _AlwaysFailEvaluator()])
        trace = _make_trace()

        # Act
        summary = suite.evaluate(trace)

        # Assert
        assert len(summary.results) == 2
        names = {r.evaluator_name for r in summary.results}
        assert "always_pass" in names
        assert "always_fail" in names

    def test_evaluation_suite_calculates_level_scores(self) -> None:
        # Arrange
        suite = EvaluationSuite(evaluators=[_AlwaysPassEvaluator(), _AlwaysFailEvaluator()])
        trace = _make_trace()

        # Act
        summary = suite.evaluate(trace)

        # Assert
        assert summary.level_scores[EvalLevel.BEHAVIOR] == 1.0
        assert summary.level_scores[EvalLevel.RISK] == 0.0

    def test_evaluation_suite_calculates_overall_score(self) -> None:
        # Arrange: BEHAVIOR=1.0, RISK=0.0 with weights 0.30 and 0.25
        suite = EvaluationSuite(evaluators=[_AlwaysPassEvaluator(), _AlwaysFailEvaluator()])
        trace = _make_trace()

        # Act
        summary = suite.evaluate(trace)

        # Assert: weighted sum / total_weight = (1.0*0.30 + 0.0*0.25) / (0.30+0.25)
        expected_score = (1.0 * 0.30 + 0.0 * 0.25) / (0.30 + 0.25)
        assert abs(summary.overall_score - expected_score) < 0.001

    def test_evaluation_suite_custom_evaluator(self) -> None:
        # Arrange
        suite = EvaluationSuite(evaluators=[])
        suite.add_evaluator(_AlwaysPassEvaluator())
        trace = _make_trace()

        # Act
        summary = suite.evaluate(trace)

        # Assert
        assert len(summary.results) == 1
        assert summary.results[0].evaluator_name == "always_pass"

    def test_evaluation_suite_remove_evaluator(self) -> None:
        # Arrange
        suite = EvaluationSuite(evaluators=[_AlwaysPassEvaluator(), _AlwaysFailEvaluator()])
        suite.remove_evaluator("always_fail")
        trace = _make_trace()

        # Act
        summary = suite.evaluate(trace)

        # Assert
        assert all(r.evaluator_name != "always_fail" for r in summary.results)
        assert len(summary.results) == 1

    def test_evaluation_suite_default_evaluators_run(self) -> None:
        # Arrange
        suite = EvaluationSuite()
        trace = _make_trace()

        # Act
        summary = suite.evaluate(trace)

        # Assert
        assert len(summary.results) > 0
        assert summary.trace_id == trace.id
        assert summary.task == trace.task

    def test_evaluation_suite_summary_trace_metadata(self) -> None:
        # Arrange
        suite = EvaluationSuite(evaluators=[_AlwaysPassEvaluator()])
        trace = _make_trace()

        # Act
        summary = suite.evaluate(trace)

        # Assert
        assert summary.trace_id == "trace001"
        assert summary.task == "test task"
        assert summary.timestamp.tzinfo is not None
