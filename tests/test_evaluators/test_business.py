"""Tests for business-level evaluators."""

from __future__ import annotations

from agentlens.evaluators.business import HumanHandoffEvaluator, TaskCompletionEvaluator
from agentlens.models.expectation import TaskExpectation
from agentlens.models.trace import SpanType, Trace
from tests.test_evaluators.conftest import make_span, make_trace


def _make_trace_from_types(
    final_output: str | None = "done",
    span_types: list[SpanType] | None = None,
) -> Trace:
    """Build a Trace from a list of SpanTypes, matching original test_business helper."""
    types = span_types or [SpanType.LLM_CALL]
    spans = [make_span(f"s{i}", st, f"step_{i}", offset_ms=i * 100) for i, st in enumerate(types)]
    return make_trace(spans, final_output=final_output, total_duration_ms=len(types) * 100)


class TestTaskCompletionEvaluator:
    def test_task_completion_with_matching_output_scores_1(self) -> None:
        # Arrange
        trace = _make_trace_from_types(final_output="The answer is 42")
        expected = TaskExpectation(expected_output="answer is 42")
        ev = TaskCompletionEvaluator()

        # Act
        results = ev.evaluate(trace, expected)
        # Assert
        assert len(results) == 1
        assert results[0].score == 1.0
        assert results[0].passed is True

    def test_task_completion_with_no_output_scores_0(self) -> None:
        # Arrange
        trace = _make_trace_from_types(final_output=None)
        ev = TaskCompletionEvaluator()

        # Act
        results = ev.evaluate(trace, None)
        # Assert
        assert results[0].score == 0.0
        assert results[0].passed is False

    def test_task_completion_with_partial_match_scores_half(self) -> None:
        # Arrange
        trace = _make_trace_from_types(final_output="Some unrelated output")
        expected = TaskExpectation(expected_output="expected answer")
        ev = TaskCompletionEvaluator()

        # Act
        results = ev.evaluate(trace, expected)
        # Assert
        assert results[0].score == 0.5
        assert results[0].passed is True

    def test_task_completion_no_expectation_with_output_scores_1(self) -> None:
        # Arrange
        trace = _make_trace_from_types(final_output="Some output")
        ev = TaskCompletionEvaluator()

        # Act
        results = ev.evaluate(trace, None)
        # Assert
        assert results[0].score == 1.0
        assert results[0].passed is True


class TestHumanHandoffEvaluator:
    def test_human_handoff_expected_and_found_passes(self) -> None:
        # Arrange
        trace = _make_trace_from_types(span_types=[SpanType.LLM_CALL, SpanType.ESCALATION])
        expected = TaskExpectation(expected_escalation=True)
        ev = HumanHandoffEvaluator()

        # Act
        results = ev.evaluate(trace, expected)
        # Assert
        assert results[0].score == 1.0
        assert results[0].passed is True

    def test_human_handoff_unexpected_escalation_fails(self) -> None:
        # Arrange
        trace = _make_trace_from_types(span_types=[SpanType.LLM_CALL, SpanType.ESCALATION])
        expected = TaskExpectation(expected_escalation=False)
        ev = HumanHandoffEvaluator()

        # Act
        results = ev.evaluate(trace, expected)
        # Assert
        assert results[0].score == 0.0
        assert results[0].passed is False

    def test_human_handoff_not_expected_and_not_found_passes(self) -> None:
        # Arrange
        trace = _make_trace_from_types(span_types=[SpanType.LLM_CALL])
        expected = TaskExpectation(expected_escalation=False)
        ev = HumanHandoffEvaluator()

        # Act
        results = ev.evaluate(trace, expected)
        # Assert
        assert results[0].score == 1.0
        assert results[0].passed is True

    def test_human_handoff_expected_but_not_found_fails(self) -> None:
        # Arrange
        trace = _make_trace_from_types(span_types=[SpanType.LLM_CALL])
        expected = TaskExpectation(expected_escalation=True)
        ev = HumanHandoffEvaluator()

        # Act
        results = ev.evaluate(trace, expected)
        # Assert
        assert results[0].score == 0.0
        assert results[0].passed is False
