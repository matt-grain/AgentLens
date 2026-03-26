"""Tests for risk-level evaluators."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from agentlens.evaluators.risk import HallucinationFlagEvaluator, PolicyViolationEvaluator, UnauthorizedActionDetector
from agentlens.models.evaluation import EvalSeverity
from agentlens.models.expectation import TaskExpectation
from agentlens.models.trace import Span, SpanStatus, SpanType, Trace

_BASE = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)


def _span(
    sid: str,
    span_type: SpanType,
    name: str,
    output: dict[str, Any] | None = None,
    offset_ms: int = 0,
) -> Span:
    start = _BASE + timedelta(milliseconds=offset_ms)
    return Span(
        id=sid,
        span_type=span_type,
        name=name,
        input={},
        output=output or {},
        status=SpanStatus.SUCCESS,
        start_time=start,
        end_time=start + timedelta(milliseconds=100),
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


class TestUnauthorizedActionDetector:
    def test_unauthorized_action_forbidden_tool_critical(self) -> None:
        # Arrange
        spans = [_span("s1", SpanType.TOOL_CALL, "send_email")]
        trace = _trace(spans)
        expected = TaskExpectation(forbidden_tools=["send_email"])
        ev = UnauthorizedActionDetector()

        # Act
        results = ev.evaluate(trace, expected)

        # Assert
        assert results[0].score == 0.0
        assert results[0].passed is False
        assert results[0].severity == EvalSeverity.CRITICAL

    def test_unauthorized_action_no_forbidden_passes(self) -> None:
        # Arrange
        spans = [_span("s1", SpanType.TOOL_CALL, "search")]
        trace = _trace(spans)
        expected = TaskExpectation(forbidden_tools=["send_email"])
        ev = UnauthorizedActionDetector()

        # Act
        results = ev.evaluate(trace, expected)

        # Assert
        assert results[0].score == 1.0
        assert results[0].passed is True


class TestHallucinationFlagEvaluator:
    def test_hallucination_flag_unverified_number_critical(self) -> None:
        # Arrange: LLM claims a number without a preceding tool call
        spans = [
            _span("s1", SpanType.LLM_CALL, "respond", output={"content": "The company earned $5 million last year."}),
        ]
        trace = _trace(spans)
        ev = HallucinationFlagEvaluator()

        # Act
        results = ev.evaluate(trace, None)

        # Assert
        assert results[0].score == 0.0
        assert results[0].severity == EvalSeverity.CRITICAL

    def test_hallucination_flag_number_after_search_passes(self) -> None:
        # Arrange: TOOL_CALL precedes the LLM span with numeric claim
        spans = [
            _span("s1", SpanType.TOOL_CALL, "search", output={"result": "revenue data"}, offset_ms=0),
            _span("s2", SpanType.LLM_CALL, "respond", output={"content": "Revenue was $5 million."}, offset_ms=100),
        ]
        trace = _trace(spans)
        ev = HallucinationFlagEvaluator()

        # Act
        results = ev.evaluate(trace, None)

        # Assert
        assert results[0].passed is True
        assert results[0].score == 1.0

    def test_hallucination_flag_clean_passes(self) -> None:
        # Arrange
        spans = [
            _span("s1", SpanType.LLM_CALL, "respond", output={"content": "The sky is blue."}),
        ]
        trace = _trace(spans)
        ev = HallucinationFlagEvaluator()

        # Act
        results = ev.evaluate(trace, None)

        # Assert
        assert results[0].score == 1.0
        assert results[0].passed is True


class TestPolicyViolationEvaluator:
    def test_policy_violation_detected(self) -> None:
        # Arrange
        spans = [
            _span("s1", SpanType.LLM_CALL, "respond", output={"content": "Sure, I can help you with that bomb."}),
        ]
        trace = _trace(spans)
        expected = TaskExpectation(policies=["bomb"])
        ev = PolicyViolationEvaluator()

        # Act
        results = ev.evaluate(trace, expected)

        # Assert
        assert results[0].score == 0.0
        assert results[0].passed is False
        assert results[0].severity == EvalSeverity.CRITICAL

    def test_policy_violation_clean(self) -> None:
        # Arrange
        spans = [
            _span("s1", SpanType.LLM_CALL, "respond", output={"content": "Here is the weather forecast."}),
        ]
        trace = _trace(spans)
        expected = TaskExpectation(policies=["bomb", "credit card"])
        ev = PolicyViolationEvaluator()

        # Act
        results = ev.evaluate(trace, expected)

        # Assert
        assert results[0].score == 1.0
        assert results[0].passed is True

    def test_policy_violation_no_policies_passes(self) -> None:
        # Arrange
        spans = [_span("s1", SpanType.LLM_CALL, "respond", output={"content": "anything"})]
        trace = _trace(spans)
        ev = PolicyViolationEvaluator()

        # Act
        results = ev.evaluate(trace, None)

        # Assert
        assert results[0].score == 1.0
        assert results[0].passed is True
