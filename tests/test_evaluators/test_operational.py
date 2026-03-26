"""Tests for operational-level evaluators."""

from __future__ import annotations

from agentlens.evaluators.operational import CostEvaluator, LatencyEvaluator, VarianceEvaluator
from agentlens.models.trace import SpanType, TokenUsage
from tests.test_evaluators.conftest import make_span, make_trace


class TestLatencyEvaluator:
    def test_latency_fast_scores_1(self) -> None:
        # Arrange: 2 second trace
        spans = [make_span("s1", SpanType.LLM_CALL, "step_s1", duration_ms=2000)]
        trace = make_trace(spans, total_duration_ms=2000)
        ev = LatencyEvaluator()

        # Act
        results = ev.evaluate(trace, None)

        # Assert
        assert results[0].score == 1.0
        assert results[0].passed is True

    def test_latency_slow_degrades(self) -> None:
        # Arrange: 35 second trace
        spans = [make_span("s1", SpanType.LLM_CALL, "step_s1", duration_ms=35000)]
        trace = make_trace(spans, total_duration_ms=35000)
        ev = LatencyEvaluator()

        # Act
        results = ev.evaluate(trace, None)

        # Assert
        assert results[0].score == 0.3
        assert results[0].passed is False

    def test_latency_medium_scores_point_8(self) -> None:
        # Arrange: 7 second trace
        spans = [make_span("s1", SpanType.LLM_CALL, "step_s1", duration_ms=7000)]
        trace = make_trace(spans, total_duration_ms=7000)
        ev = LatencyEvaluator()

        # Act
        results = ev.evaluate(trace, None)

        # Assert
        assert results[0].score == 0.8
        assert results[0].passed is True


class TestCostEvaluator:
    def test_cost_low_tokens_scores_1(self) -> None:
        # Arrange: 100 input + 50 output tokens => $0.001 + $0.0015 = $0.0025
        spans = [
            make_span(
                "s1",
                SpanType.LLM_CALL,
                "step_s1",
                duration_ms=100,
                token_usage=TokenUsage(input_tokens=100, output_tokens=50),
            )
        ]
        trace = make_trace(spans, total_duration_ms=100)
        ev = CostEvaluator()

        # Act
        results = ev.evaluate(trace, None)

        # Assert
        assert results[0].score == 1.0
        assert results[0].passed is True

    def test_cost_high_tokens_degrades(self) -> None:
        # Arrange: 5000 input + 2000 output tokens => $0.05 + $0.06 = $0.11
        spans = [
            make_span(
                "s1",
                SpanType.LLM_CALL,
                "step_s1",
                duration_ms=100,
                token_usage=TokenUsage(input_tokens=5000, output_tokens=2000),
            )
        ]
        trace = make_trace(spans, total_duration_ms=100)
        ev = CostEvaluator()

        # Act
        results = ev.evaluate(trace, None)

        # Assert
        assert results[0].score == 0.3
        assert results[0].passed is False

    def test_cost_no_tokens_scores_1(self) -> None:
        # Arrange
        spans = [make_span("s1", SpanType.LLM_CALL, "step_s1", duration_ms=100)]
        trace = make_trace(spans, total_duration_ms=100)
        ev = CostEvaluator()

        # Act
        results = ev.evaluate(trace, None)

        # Assert
        assert results[0].score == 1.0
        assert results[0].passed is True


class TestVarianceEvaluator:
    def test_variance_consistent_scores_1(self) -> None:
        # Arrange: all spans take same duration — CV = 0
        spans = [
            make_span(f"s{i}", SpanType.LLM_CALL, f"step_s{i}", duration_ms=100, offset_ms=i * 100) for i in range(4)
        ]
        trace = make_trace(spans, total_duration_ms=400)
        ev = VarianceEvaluator()

        # Act
        results = ev.evaluate(trace, None)

        # Assert
        assert results[0].score == 1.0
        assert results[0].passed is True

    def test_variance_erratic_degrades(self) -> None:
        # Arrange: one very slow span (100s) among 5 fast spans (1ms) — CV > 2
        spans = [
            make_span("s1", SpanType.LLM_CALL, "step_s1", duration_ms=1, offset_ms=0),
            make_span("s2", SpanType.LLM_CALL, "step_s2", duration_ms=1, offset_ms=1),
            make_span("s3", SpanType.LLM_CALL, "step_s3", duration_ms=1, offset_ms=2),
            make_span("s4", SpanType.LLM_CALL, "step_s4", duration_ms=1, offset_ms=3),
            make_span("s5", SpanType.LLM_CALL, "step_s5", duration_ms=1, offset_ms=4),
            make_span("s6", SpanType.LLM_CALL, "step_s6", duration_ms=100000, offset_ms=5),
        ]
        trace = make_trace(spans, total_duration_ms=100005)
        ev = VarianceEvaluator()

        # Act
        results = ev.evaluate(trace, None)

        # Assert
        assert results[0].score <= 0.5
        assert results[0].passed is False

    def test_variance_single_span_scores_1(self) -> None:
        # Arrange
        spans = [make_span("s1", SpanType.LLM_CALL, "step_s1", duration_ms=500)]
        trace = make_trace(spans, total_duration_ms=500)
        ev = VarianceEvaluator()

        # Act
        results = ev.evaluate(trace, None)

        # Assert
        assert results[0].score == 1.0
        assert results[0].passed is True
