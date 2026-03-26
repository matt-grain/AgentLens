"""Tests for behavior-level evaluators."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from agentlens.evaluators.behavior import (
    LoopDetector,
    RecoveryEvaluator,
    StepEfficiencyEvaluator,
    ToolSelectionEvaluator,
)
from agentlens.models.evaluation import EvalSeverity
from agentlens.models.expectation import TaskExpectation
from agentlens.models.trace import Span, SpanStatus, SpanType, Trace

_BASE = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)


def _span(
    sid: str,
    span_type: SpanType,
    name: str,
    inp: dict[str, Any] | None = None,
    status: SpanStatus = SpanStatus.SUCCESS,
    offset_ms: int = 0,
    duration_ms: int = 100,
) -> Span:
    start = _BASE + timedelta(milliseconds=offset_ms)
    return Span(
        id=sid,
        span_type=span_type,
        name=name,
        input=inp or {},
        output={"content": "ok"},
        status=status,
        start_time=start,
        end_time=start + timedelta(milliseconds=duration_ms),
    )


def _trace(spans: list[Span]) -> Trace:
    end = spans[-1].end_time if spans else _BASE
    return Trace(
        id="t1",
        task="test",
        agent_name="agent",
        spans=spans,
        final_output="done",
        started_at=_BASE,
        completed_at=end,
    )


class TestToolSelectionEvaluator:
    def test_tool_selection_all_expected_used_scores_1(self) -> None:
        # Arrange
        spans = [
            _span("s1", SpanType.TOOL_CALL, "search"),
            _span("s2", SpanType.TOOL_CALL, "calculator"),
        ]
        trace = _trace(spans)
        expected = TaskExpectation(expected_tools=["search", "calculator"])
        ev = ToolSelectionEvaluator()

        # Act
        results = ev.evaluate(trace, expected)

        # Assert
        assert results[0].score == 1.0
        assert results[0].passed is True

    def test_tool_selection_forbidden_tool_used_lowers_score(self) -> None:
        # Arrange
        spans = [_span("s1", SpanType.TOOL_CALL, "send_email")]
        trace = _trace(spans)
        expected = TaskExpectation(forbidden_tools=["send_email"])
        ev = ToolSelectionEvaluator()

        # Act
        results = ev.evaluate(trace, expected)

        # Assert
        assert results[0].score < 1.0
        assert results[0].passed is False

    def test_tool_selection_no_expectation_scores_1(self) -> None:
        # Arrange
        spans = [_span("s1", SpanType.TOOL_CALL, "anything")]
        trace = _trace(spans)
        ev = ToolSelectionEvaluator()

        # Act
        results = ev.evaluate(trace, None)

        # Assert
        assert results[0].score == 1.0


class TestStepEfficiencyEvaluator:
    def test_step_efficiency_under_max_scores_1(self) -> None:
        # Arrange
        spans = [_span(f"s{i}", SpanType.LLM_CALL, f"step_{i}", offset_ms=i * 100) for i in range(3)]
        trace = _trace(spans)
        expected = TaskExpectation(max_steps=5)
        ev = StepEfficiencyEvaluator()

        # Act
        results = ev.evaluate(trace, expected)

        # Assert
        assert results[0].score == 1.0
        assert results[0].passed is True

    def test_step_efficiency_over_max_degrades(self) -> None:
        # Arrange
        spans = [_span(f"s{i}", SpanType.LLM_CALL, f"step_{i}", offset_ms=i * 100) for i in range(10)]
        trace = _trace(spans)
        expected = TaskExpectation(max_steps=5)
        ev = StepEfficiencyEvaluator()

        # Act
        results = ev.evaluate(trace, expected)

        # Assert
        assert results[0].score < 1.0
        assert results[0].passed is False


class TestLoopDetector:
    def test_loop_detector_no_loops_scores_1(self) -> None:
        # Arrange
        spans = [
            _span("s1", SpanType.LLM_CALL, "plan", inp={"q": "a"}),
            _span("s2", SpanType.TOOL_CALL, "search", inp={"q": "b"}),
            _span("s3", SpanType.LLM_CALL, "synthesize", inp={"q": "c"}),
        ]
        trace = _trace(spans)
        ev = LoopDetector()

        # Act
        results = ev.evaluate(trace, None)

        # Assert
        assert results[0].score == 1.0
        assert results[0].passed is True

    def test_loop_detector_duplicate_detected(self) -> None:
        # Arrange
        spans = [
            _span("s1", SpanType.TOOL_CALL, "search", inp={"q": "same"}),
            _span("s2", SpanType.TOOL_CALL, "search", inp={"q": "same"}),
        ]
        trace = _trace(spans)
        ev = LoopDetector()

        # Act
        results = ev.evaluate(trace, None)

        # Assert
        assert results[0].score < 1.0
        assert results[0].severity == EvalSeverity.WARNING

    def test_loop_detector_cycle_detected_critical(self) -> None:
        # Arrange: A -> B -> A (same fingerprint reused non-consecutively)
        spans = [
            _span("s1", SpanType.TOOL_CALL, "search", inp={"q": "a"}),
            _span("s2", SpanType.LLM_CALL, "think", inp={"q": "b"}),
            _span("s3", SpanType.TOOL_CALL, "search", inp={"q": "a"}),
        ]
        trace = _trace(spans)
        ev = LoopDetector()

        # Act
        results = ev.evaluate(trace, None)

        # Assert
        assert results[0].score == 0.0
        assert results[0].severity == EvalSeverity.CRITICAL


class TestRecoveryEvaluator:
    def test_recovery_after_failure_passes(self) -> None:
        # Arrange
        spans = [
            _span("s1", SpanType.TOOL_CALL, "search", status=SpanStatus.FAILURE),
            _span("s2", SpanType.TOOL_CALL, "fallback_search"),
        ]
        trace = _trace(spans)
        ev = RecoveryEvaluator()

        # Act
        results = ev.evaluate(trace, None)

        # Assert
        assert results[0].score == 1.0
        assert results[0].passed is True

    def test_recovery_no_attempt_fails(self) -> None:
        # Arrange: failure is the last span — no recovery
        spans = [
            _span("s1", SpanType.TOOL_CALL, "search"),
            _span("s2", SpanType.TOOL_CALL, "search", status=SpanStatus.FAILURE),
        ]
        trace = _trace(spans)
        ev = RecoveryEvaluator()

        # Act
        results = ev.evaluate(trace, None)

        # Assert
        assert results[0].score == 0.0
        assert results[0].passed is False

    def test_recovery_no_failures_scores_1(self) -> None:
        # Arrange
        spans = [_span("s1", SpanType.LLM_CALL, "plan")]
        trace = _trace(spans)
        ev = RecoveryEvaluator()

        # Act
        results = ev.evaluate(trace, None)

        # Assert
        assert results[0].score == 1.0
        assert results[0].passed is True
