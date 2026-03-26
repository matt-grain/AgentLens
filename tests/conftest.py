from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from agentlens.models.evaluation import EvalLevel, EvalResult, EvalSeverity, EvalSummary
from agentlens.models.expectation import TaskExpectation
from agentlens.models.trace import Span, SpanStatus, SpanType, TokenUsage, Trace


@pytest.fixture
def sample_span() -> Span:
    base = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    return Span(
        id="span001",
        span_type=SpanType.LLM_CALL,
        name="plan",
        input={"messages": [{"role": "user", "content": "test"}]},
        output={"content": "I'll help with that"},
        status=SpanStatus.SUCCESS,
        start_time=base,
        end_time=base + timedelta(milliseconds=500),
        token_usage=TokenUsage(input_tokens=50, output_tokens=25),
    )


@pytest.fixture
def sample_trace() -> Trace:
    base = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

    span1 = Span(
        id="span001",
        span_type=SpanType.LLM_CALL,
        name="plan",
        input={"messages": [{"role": "user", "content": "test"}]},
        output={"content": "I'll plan my approach"},
        status=SpanStatus.SUCCESS,
        start_time=base,
        end_time=base + timedelta(milliseconds=200),
        token_usage=TokenUsage(input_tokens=50, output_tokens=25),
    )
    span2 = Span(
        id="span002",
        span_type=SpanType.TOOL_CALL,
        name="search",
        input={"query": "test"},
        output={"result": "found"},
        status=SpanStatus.SUCCESS,
        start_time=base + timedelta(milliseconds=200),
        end_time=base + timedelta(milliseconds=400),
    )
    span3 = Span(
        id="span003",
        span_type=SpanType.LLM_CALL,
        name="synthesize",
        input={"messages": [{"role": "user", "content": "summarize"}]},
        output={"content": "Here is the answer based on my research."},
        status=SpanStatus.SUCCESS,
        start_time=base + timedelta(milliseconds=400),
        end_time=base + timedelta(milliseconds=600),
        token_usage=TokenUsage(input_tokens=80, output_tokens=40),
    )

    return Trace(
        id="trace001",
        task="Research task",
        agent_name="research-agent",
        spans=[span1, span2, span3],
        final_output="Here is the answer based on my research.",
        started_at=base,
        completed_at=base + timedelta(milliseconds=600),
    )


@pytest.fixture
def sample_expectation() -> TaskExpectation:
    return TaskExpectation(
        expected_tools=["search", "calculator"],
        forbidden_tools=["send_email"],
        max_steps=5,
    )


@pytest.fixture
def sample_eval_summary() -> EvalSummary:
    results = [
        EvalResult(
            evaluator_name="tool_use",
            level=EvalLevel.BEHAVIOR,
            score=1.0,
            passed=True,
            message="All tools used correctly",
            severity=EvalSeverity.INFO,
        ),
        EvalResult(
            evaluator_name="policy_check",
            level=EvalLevel.RISK,
            score=0.0,
            passed=False,
            message="Policy violated",
            severity=EvalSeverity.CRITICAL,
        ),
    ]
    return EvalSummary(
        trace_id="trace001",
        task="Research task",
        results=results,
        level_scores={EvalLevel.BEHAVIOR: 1.0, EvalLevel.RISK: 0.0},
        overall_score=0.5,
        timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
    )
