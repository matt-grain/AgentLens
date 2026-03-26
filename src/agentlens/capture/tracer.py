from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Self

from agentlens.models.trace import Span, SpanStatus, SpanType, TokenUsage, Trace


class SpanBuilder:
    """Deferred span — records start time immediately, completed on explicit call."""

    def __init__(
        self,
        tracer: Tracer,
        span_type: SpanType,
        name: str,
        input: dict[str, Any],
        metadata: dict[str, Any] | None = None,
        parent_id: str | None = None,
    ) -> None:
        self._tracer = tracer
        self._span_type = span_type
        self._name = name
        self._input = input
        self._metadata = metadata or {}
        self._parent_id = parent_id
        self._span_id = uuid.uuid4().hex[:12]
        self._start_time = datetime.now(UTC)

    def complete(
        self,
        output: dict[str, Any] | None = None,
        status: SpanStatus = SpanStatus.SUCCESS,
        token_usage: TokenUsage | None = None,
    ) -> Span:
        end_time = datetime.now(UTC)
        span = Span(
            id=self._span_id,
            span_type=self._span_type,
            name=self._name,
            input=self._input,
            output=output,
            status=status,
            start_time=self._start_time,
            end_time=end_time,
            metadata=self._metadata,
            parent_id=self._parent_id,
            token_usage=token_usage,
        )
        self._tracer.append_span(span)
        return span


class Tracer:
    """Context manager for building traces via manual instrumentation.

    Not thread-safe — intended for single-threaded agent execution.
    """

    def __init__(self, task: str, agent_name: str) -> None:
        self._task = task
        self._agent_name = agent_name
        self._trace_id = uuid.uuid4().hex[:12]
        self._spans: list[Span] = []
        self._started_at: datetime | None = None
        self._completed_at: datetime | None = None

    def __enter__(self) -> Self:
        self._started_at = datetime.now(UTC)
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self._completed_at = datetime.now(UTC)

    def append_span(self, span: Span) -> None:
        """Append a span to the trace. Used by SpanBuilder."""
        self._spans.append(span)

    @property
    def trace_id(self) -> str:
        return self._trace_id

    def add_span(
        self,
        span_type: SpanType,
        name: str,
        input: dict[str, Any],
        output: dict[str, Any] | None = None,
        status: SpanStatus = SpanStatus.SUCCESS,
        metadata: dict[str, Any] | None = None,
        parent_id: str | None = None,
        token_usage: TokenUsage | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> Span:
        now = datetime.now(UTC)
        span = Span(
            id=uuid.uuid4().hex[:12],
            span_type=span_type,
            name=name,
            input=input,
            output=output,
            status=status,
            start_time=start_time or now,
            end_time=end_time or now,
            metadata=metadata or {},
            parent_id=parent_id,
            token_usage=token_usage,
        )
        self._spans.append(span)
        return span

    def start_span(
        self,
        span_type: SpanType,
        name: str,
        input: dict[str, Any],
        metadata: dict[str, Any] | None = None,
        parent_id: str | None = None,
    ) -> SpanBuilder:
        return SpanBuilder(
            tracer=self,
            span_type=span_type,
            name=name,
            input=input,
            metadata=metadata,
            parent_id=parent_id,
        )

    def get_trace(self) -> Trace:
        if self._completed_at is None:
            raise RuntimeError("Tracer must be used as a context manager and exited before calling get_trace()")
        if self._started_at is None:
            raise RuntimeError("Tracer was not entered as context manager")
        return Trace(
            id=self._trace_id,
            task=self._task,
            agent_name=self._agent_name,
            spans=list(self._spans),
            started_at=self._started_at,
            completed_at=self._completed_at,
        )
