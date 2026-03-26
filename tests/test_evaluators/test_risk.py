"""Tests for risk-level evaluators."""

from __future__ import annotations

from agentlens.evaluators.risk import HallucinationFlagEvaluator, PolicyViolationEvaluator, UnauthorizedActionDetector
from agentlens.models.evaluation import EvalSeverity
from agentlens.models.expectation import TaskExpectation
from agentlens.models.trace import SpanType
from tests.test_evaluators.conftest import make_span, make_trace


class TestUnauthorizedActionDetector:
    def test_unauthorized_action_forbidden_tool_critical(self) -> None:
        # Arrange
        spans = [make_span("s1", SpanType.TOOL_CALL, "send_email")]
        trace = make_trace(spans)
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
        spans = [make_span("s1", SpanType.TOOL_CALL, "search")]
        trace = make_trace(spans)
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
            make_span(
                "s1",
                SpanType.LLM_CALL,
                "respond",
                output={"content": "The company earned $5 million last year."},
            ),
        ]
        trace = make_trace(spans)
        ev = HallucinationFlagEvaluator()

        # Act
        results = ev.evaluate(trace, None)

        # Assert
        assert results[0].score == 0.0
        assert results[0].severity == EvalSeverity.CRITICAL

    def test_hallucination_flag_number_after_search_passes(self) -> None:
        # Arrange: TOOL_CALL precedes the LLM span with numeric claim
        spans = [
            make_span("s1", SpanType.TOOL_CALL, "search", output={"result": "revenue data"}, offset_ms=0),
            make_span("s2", SpanType.LLM_CALL, "respond", output={"content": "Revenue was $5 million."}, offset_ms=100),
        ]
        trace = make_trace(spans)
        ev = HallucinationFlagEvaluator()

        # Act
        results = ev.evaluate(trace, None)

        # Assert
        assert results[0].passed is True
        assert results[0].score == 1.0

    def test_hallucination_flag_clean_passes(self) -> None:
        # Arrange
        spans = [
            make_span("s1", SpanType.LLM_CALL, "respond", output={"content": "The sky is blue."}),
        ]
        trace = make_trace(spans)
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
            make_span("s1", SpanType.LLM_CALL, "respond", output={"content": "Sure, I can help you with that bomb."}),
        ]
        trace = make_trace(spans)
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
            make_span("s1", SpanType.LLM_CALL, "respond", output={"content": "Here is the weather forecast."}),
        ]
        trace = make_trace(spans)
        expected = TaskExpectation(policies=["bomb", "credit card"])
        ev = PolicyViolationEvaluator()

        # Act
        results = ev.evaluate(trace, expected)

        # Assert
        assert results[0].score == 1.0
        assert results[0].passed is True

    def test_policy_violation_no_policies_passes(self) -> None:
        # Arrange
        spans = [make_span("s1", SpanType.LLM_CALL, "respond", output={"content": "anything"})]
        trace = make_trace(spans)
        ev = PolicyViolationEvaluator()

        # Act
        results = ev.evaluate(trace, None)

        # Assert
        assert results[0].score == 1.0
        assert results[0].passed is True
