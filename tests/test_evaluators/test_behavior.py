"""Tests for behavior-level evaluators."""

from __future__ import annotations

from agentlens.evaluators.behavior import (
    LoopDetector,
    RecoveryEvaluator,
    StepEfficiencyEvaluator,
    ToolSelectionEvaluator,
)
from agentlens.models.evaluation import EvalSeverity
from agentlens.models.expectation import TaskExpectation
from agentlens.models.trace import SpanStatus, SpanType
from tests.test_evaluators.conftest import make_span, make_trace


class TestToolSelectionEvaluator:
    def test_tool_selection_all_expected_used_scores_1(self) -> None:
        # Arrange
        spans = [
            make_span("s1", SpanType.TOOL_CALL, "search"),
            make_span("s2", SpanType.TOOL_CALL, "calculator"),
        ]
        trace = make_trace(spans)
        expected = TaskExpectation(expected_tools=["search", "calculator"])
        ev = ToolSelectionEvaluator()

        # Act
        results = ev.evaluate(trace, expected)

        # Assert
        assert results[0].score == 1.0
        assert results[0].passed is True

    def test_tool_selection_forbidden_tool_used_lowers_score(self) -> None:
        # Arrange
        spans = [make_span("s1", SpanType.TOOL_CALL, "send_email")]
        trace = make_trace(spans)
        expected = TaskExpectation(forbidden_tools=["send_email"])
        ev = ToolSelectionEvaluator()

        # Act
        results = ev.evaluate(trace, expected)

        # Assert
        assert results[0].score < 1.0
        assert results[0].passed is False

    def test_tool_selection_no_expectation_scores_1(self) -> None:
        # Arrange
        spans = [make_span("s1", SpanType.TOOL_CALL, "anything")]
        trace = make_trace(spans)
        ev = ToolSelectionEvaluator()

        # Act
        results = ev.evaluate(trace, None)

        # Assert
        assert results[0].score == 1.0


class TestStepEfficiencyEvaluator:
    def test_step_efficiency_under_max_scores_1(self) -> None:
        # Arrange
        spans = [make_span(f"s{i}", SpanType.LLM_CALL, f"step_{i}", offset_ms=i * 100) for i in range(3)]
        trace = make_trace(spans)
        expected = TaskExpectation(max_steps=5)
        ev = StepEfficiencyEvaluator()

        # Act
        results = ev.evaluate(trace, expected)

        # Assert
        assert results[0].score == 1.0
        assert results[0].passed is True

    def test_step_efficiency_over_max_degrades(self) -> None:
        # Arrange
        spans = [make_span(f"s{i}", SpanType.LLM_CALL, f"step_{i}", offset_ms=i * 100) for i in range(10)]
        trace = make_trace(spans)
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
            make_span("s1", SpanType.LLM_CALL, "plan", inp={"q": "a"}),
            make_span("s2", SpanType.TOOL_CALL, "search", inp={"q": "b"}),
            make_span("s3", SpanType.LLM_CALL, "synthesize", inp={"q": "c"}),
        ]
        trace = make_trace(spans)
        ev = LoopDetector()

        # Act
        results = ev.evaluate(trace, None)

        # Assert
        assert results[0].score == 1.0
        assert results[0].passed is True

    def test_loop_detector_duplicate_detected(self) -> None:
        # Arrange
        spans = [
            make_span("s1", SpanType.TOOL_CALL, "search", inp={"q": "same"}),
            make_span("s2", SpanType.TOOL_CALL, "search", inp={"q": "same"}),
        ]
        trace = make_trace(spans)
        ev = LoopDetector()

        # Act
        results = ev.evaluate(trace, None)

        # Assert
        assert results[0].score < 1.0
        assert results[0].severity == EvalSeverity.WARNING

    def test_loop_detector_cycle_detected_critical(self) -> None:
        # Arrange: A -> B -> A (same fingerprint reused non-consecutively)
        spans = [
            make_span("s1", SpanType.TOOL_CALL, "search", inp={"q": "a"}),
            make_span("s2", SpanType.LLM_CALL, "think", inp={"q": "b"}),
            make_span("s3", SpanType.TOOL_CALL, "search", inp={"q": "a"}),
        ]
        trace = make_trace(spans)
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
            make_span("s1", SpanType.TOOL_CALL, "search", status=SpanStatus.FAILURE),
            make_span("s2", SpanType.TOOL_CALL, "fallback_search"),
        ]
        trace = make_trace(spans)
        ev = RecoveryEvaluator()

        # Act
        results = ev.evaluate(trace, None)

        # Assert
        assert results[0].score == 1.0
        assert results[0].passed is True

    def test_recovery_no_attempt_fails(self) -> None:
        # Arrange: failure is the last span — no recovery
        spans = [
            make_span("s1", SpanType.TOOL_CALL, "search"),
            make_span("s2", SpanType.TOOL_CALL, "search", status=SpanStatus.FAILURE),
        ]
        trace = make_trace(spans)
        ev = RecoveryEvaluator()

        # Act
        results = ev.evaluate(trace, None)

        # Assert
        assert results[0].score == 0.0
        assert results[0].passed is False

    def test_recovery_no_failures_scores_1(self) -> None:
        # Arrange
        spans = [make_span("s1", SpanType.LLM_CALL, "plan")]
        trace = make_trace(spans)
        ev = RecoveryEvaluator()

        # Act
        results = ev.evaluate(trace, None)

        # Assert
        assert results[0].score == 1.0
        assert results[0].passed is True
