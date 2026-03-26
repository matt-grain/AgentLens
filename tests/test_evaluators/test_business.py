"""Tests for business-level evaluators."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from agentlens.evaluators.business import HumanHandoffEvaluator, TaskCompletionEvaluator
from agentlens.models.expectation import TaskExpectation
from agentlens.models.trace import Span, SpanStatus, SpanType, Trace

_BASE = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)


def _make_trace(
    final_output: str | None = "done",
    span_types: list[SpanType] | None = None,
) -> Trace:
    span_types = span_types or [SpanType.LLM_CALL]
    spans = [
        Span(
            id=f"s{i}",
            span_type=st,
            name=f"step_{i}",
            input={},
            output={"content": "ok"},
            status=SpanStatus.SUCCESS,
            start_time=_BASE + timedelta(milliseconds=i * 100),
            end_time=_BASE + timedelta(milliseconds=(i + 1) * 100),
        )
        for i, st in enumerate(span_types)
    ]
    return Trace(
        id="t1",
        task="test",
        agent_name="agent",
        spans=spans,
        final_output=final_output,
        started_at=_BASE,
        completed_at=_BASE + timedelta(milliseconds=len(spans) * 100),
    )


class TestTaskCompletionEvaluator:
    def test_task_completion_with_matching_output_scores_1(self) -> None:
        # Arrange
        trace = _make_trace(final_output="The answer is 42")
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
        trace = _make_trace(final_output=None)
        ev = TaskCompletionEvaluator()

        # Act
        results = ev.evaluate(trace, None)

        # Assert
        assert results[0].score == 0.0
        assert results[0].passed is False

    def test_task_completion_with_partial_match_scores_half(self) -> None:
        # Arrange
        trace = _make_trace(final_output="Some unrelated output")
        expected = TaskExpectation(expected_output="expected answer")
        ev = TaskCompletionEvaluator()

        # Act
        results = ev.evaluate(trace, expected)

        # Assert
        assert results[0].score == 0.5
        assert results[0].passed is True

    def test_task_completion_no_expectation_with_output_scores_1(self) -> None:
        # Arrange
        trace = _make_trace(final_output="Some output")
        ev = TaskCompletionEvaluator()

        # Act
        results = ev.evaluate(trace, None)

        # Assert
        assert results[0].score == 1.0
        assert results[0].passed is True


class TestHumanHandoffEvaluator:
    def test_human_handoff_expected_and_found_passes(self) -> None:
        # Arrange
        trace = _make_trace(span_types=[SpanType.LLM_CALL, SpanType.ESCALATION])
        expected = TaskExpectation(expected_escalation=True)
        ev = HumanHandoffEvaluator()

        # Act
        results = ev.evaluate(trace, expected)

        # Assert
        assert results[0].score == 1.0
        assert results[0].passed is True

    def test_human_handoff_unexpected_escalation_fails(self) -> None:
        # Arrange
        trace = _make_trace(span_types=[SpanType.LLM_CALL, SpanType.ESCALATION])
        expected = TaskExpectation(expected_escalation=False)
        ev = HumanHandoffEvaluator()

        # Act
        results = ev.evaluate(trace, expected)

        # Assert
        assert results[0].score == 0.0
        assert results[0].passed is False

    def test_human_handoff_not_expected_and_not_found_passes(self) -> None:
        # Arrange
        trace = _make_trace(span_types=[SpanType.LLM_CALL])
        expected = TaskExpectation(expected_escalation=False)
        ev = HumanHandoffEvaluator()

        # Act
        results = ev.evaluate(trace, expected)

        # Assert
        assert results[0].score == 1.0
        assert results[0].passed is True

    def test_human_handoff_expected_but_not_found_fails(self) -> None:
        # Arrange
        trace = _make_trace(span_types=[SpanType.LLM_CALL])
        expected = TaskExpectation(expected_escalation=True)
        ev = HumanHandoffEvaluator()

        # Act
        results = ev.evaluate(trace, expected)

        # Assert
        assert results[0].score == 0.0
        assert results[0].passed is False
