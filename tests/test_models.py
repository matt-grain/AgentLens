from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from agentlens.models.evaluation import EvalLevel, EvalResult, EvalSeverity, EvalSummary
from agentlens.models.expectation import TaskExpectation
from agentlens.models.trace import Span, SpanStatus, SpanType, Trace


def test_span_duration_ms_computed_correctly(sample_span: Span) -> None:
    assert sample_span.duration_ms == 500


def test_span_frozen_raises_on_mutation(sample_span: Span) -> None:
    with pytest.raises((ValidationError, TypeError)):
        sample_span.name = "mutated"  # type: ignore[misc]  # ty: ignore[invalid-assignment]


def test_trace_total_tokens_sums_spans(sample_trace: Trace) -> None:
    total = sample_trace.total_tokens
    assert total is not None
    # span1: 50+25=75, span2: no usage, span3: 80+40=120 → total input=130, output=65
    assert total.input_tokens == 130
    assert total.output_tokens == 65


def test_trace_total_tokens_none_when_no_usage() -> None:
    base = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    span = Span(
        id="s1",
        span_type=SpanType.TOOL_CALL,
        name="search",
        input={"query": "x"},
        output={"result": "y"},
        status=SpanStatus.SUCCESS,
        start_time=base,
        end_time=base + timedelta(milliseconds=100),
    )
    trace = Trace(
        id="t1",
        task="test",
        agent_name="agent",
        spans=[span],
        started_at=base,
        completed_at=base + timedelta(milliseconds=100),
    )
    assert trace.total_tokens is None


def test_trace_duration_ms_computed_correctly(sample_trace: Trace) -> None:
    assert sample_trace.duration_ms == 600


def test_eval_result_frozen() -> None:
    result = EvalResult(
        evaluator_name="test",
        level=EvalLevel.BUSINESS,
        score=1.0,
        passed=True,
        message="ok",
        severity=EvalSeverity.INFO,
    )
    with pytest.raises((ValidationError, TypeError)):
        result.score = 0.5  # type: ignore[misc]  # ty: ignore[invalid-assignment]


def test_eval_summary_passed_property_all_pass() -> None:
    results = [
        EvalResult(
            evaluator_name="a",
            level=EvalLevel.BEHAVIOR,
            score=1.0,
            passed=True,
            message="ok",
            severity=EvalSeverity.INFO,
        ),
        EvalResult(
            evaluator_name="b",
            level=EvalLevel.RISK,
            score=1.0,
            passed=True,
            message="ok",
            severity=EvalSeverity.INFO,
        ),
    ]
    summary = EvalSummary(
        trace_id="t1",
        task="test",
        results=results,
        level_scores={},
        overall_score=1.0,
        timestamp=datetime(2024, 1, 1, tzinfo=UTC),
    )
    assert summary.passed is True


def test_eval_summary_passed_property_one_fails() -> None:
    results = [
        EvalResult(
            evaluator_name="a",
            level=EvalLevel.BEHAVIOR,
            score=1.0,
            passed=True,
            message="ok",
            severity=EvalSeverity.INFO,
        ),
        EvalResult(
            evaluator_name="b",
            level=EvalLevel.RISK,
            score=0.0,
            passed=False,
            message="fail",
            severity=EvalSeverity.WARNING,
        ),
    ]
    summary = EvalSummary(
        trace_id="t1",
        task="test",
        results=results,
        level_scores={},
        overall_score=0.5,
        timestamp=datetime(2024, 1, 1, tzinfo=UTC),
    )
    assert summary.passed is False


def test_eval_summary_critical_failures(sample_eval_summary: EvalSummary) -> None:
    failures = sample_eval_summary.critical_failures
    assert len(failures) == 1
    assert failures[0].evaluator_name == "policy_check"
    assert failures[0].severity == EvalSeverity.CRITICAL


def test_task_expectation_defaults() -> None:
    exp = TaskExpectation()
    assert exp.expected_output is None
    assert exp.expected_tools == []
    assert exp.forbidden_tools == []
    assert exp.max_steps is None
    assert exp.policies == []
    assert exp.expected_escalation is False
