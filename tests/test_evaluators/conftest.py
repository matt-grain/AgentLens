"""Shared test factories for evaluator tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from agentlens.models.trace import Span, SpanStatus, SpanType, TokenUsage, Trace

_BASE = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)


def make_span(
    sid: str,
    span_type: SpanType,
    name: str,
    inp: dict[str, Any] | None = None,
    output: dict[str, Any] | None = None,
    status: SpanStatus = SpanStatus.SUCCESS,
    offset_ms: int = 0,
    duration_ms: int = 100,
    parent_id: str | None = None,
    token_usage: TokenUsage | None = None,
) -> Span:
    start = _BASE + timedelta(milliseconds=offset_ms)
    return Span(
        id=sid,
        span_type=span_type,
        name=name,
        input=inp or {},
        output=output if output is not None else {"content": "ok"},
        status=status,
        start_time=start,
        end_time=start + timedelta(milliseconds=duration_ms),
        parent_id=parent_id,
        token_usage=token_usage,
    )


def make_trace(
    spans: list[Span],
    task: str = "test task",
    final_output: str | None = "done",
    total_duration_ms: int | None = None,
) -> Trace:
    end_time = spans[-1].end_time if spans else _BASE
    completed_at = _BASE + timedelta(milliseconds=total_duration_ms) if total_duration_ms is not None else end_time
    return Trace(
        id="t1",
        task=task,
        agent_name="agent",
        spans=spans,
        final_output=final_output,
        started_at=_BASE,
        completed_at=completed_at,
    )
