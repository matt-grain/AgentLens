"""Trace collection — builds spans, accumulates them, finalizes traces."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agentlens.models.trace import Span, SpanStatus, SpanType, TokenUsage, Trace
from agentlens.server.models import ChatMessage, MessageRole


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _now() -> datetime:
    return datetime.now(UTC)


def _extract_agent_name(messages: list[ChatMessage]) -> str | None:
    system_msg = next((m for m in messages if m.role == MessageRole.SYSTEM), None)
    if system_msg and system_msg.content:
        text = system_msg.content
        if text.startswith("You are "):
            # CrewAI format: "You are {Role}. {backstory...}"
            end = text.find(".", 8)
            if end > 8:
                return text[8:end]
    return None


def _build_llm_span(
    messages: list[ChatMessage],
    content: str,
    tool_calls: list[dict[str, Any]],
    usage: dict[str, int],
    llm_span_id: str,
    start_time: datetime,
    agent_name: str | None = None,
) -> Span:
    last_user = next((m.content for m in reversed(messages) if m.role == MessageRole.USER), "")
    token_usage = TokenUsage(
        input_tokens=usage.get("prompt_tokens", 0),
        output_tokens=usage.get("completion_tokens", 0),
    )
    metadata: dict[str, Any] = {}
    if agent_name:
        metadata["agent_name"] = agent_name
    return Span(
        id=llm_span_id,
        span_type=SpanType.LLM_CALL,
        name="llm_call",
        input={"messages": [last_user]},
        output={"content": content, "tool_calls": tool_calls},
        status=SpanStatus.SUCCESS,
        start_time=start_time,
        end_time=_now(),
        token_usage=token_usage,
        metadata=metadata,
    )


def _build_tool_spans(tool_calls: list[dict[str, Any]], parent_id: str, start_time: datetime) -> list[Span]:
    spans: list[Span] = []
    for tc in tool_calls:
        fn = tc.get("function", {})
        spans.append(
            Span(
                id=_new_id(),
                span_type=SpanType.TOOL_CALL,
                name=fn.get("name", "unknown"),
                input={"arguments": fn.get("arguments", "")},
                output={"result": ""},
                status=SpanStatus.SUCCESS,
                start_time=start_time,
                end_time=start_time,
                parent_id=parent_id,
            )
        )
    return spans


class TraceCollector:
    """Accumulates spans during an agent turn and finalizes them into Traces."""

    def __init__(self, traces_dir: Path | None = None, session_id: str | None = None) -> None:
        self.traces: list[Trace] = []
        self.current_spans: list[Span] = []
        self.current_task: str = "unknown"
        self._traces_dir = traces_dir
        self._session_id = session_id
        if traces_dir is not None:
            traces_dir.mkdir(parents=True, exist_ok=True)

    def set_session_id(self, session_id: str) -> None:
        """Update the session ID used for subsequent finalized traces."""
        self._session_id = session_id

    def record_llm_call(
        self,
        messages: list[ChatMessage],
        content: str,
        tool_calls: list[dict[str, Any]],
        usage: dict[str, int],
        start_time: datetime | None = None,
        agent_name: str | None = None,
    ) -> None:
        if not self.current_spans:
            first_user = next((m.content for m in messages if m.role == MessageRole.USER), None)
            self.current_task = first_user or "unknown"

        actual_start = start_time if start_time is not None else _now()
        if agent_name is None:
            agent_name = _extract_agent_name(messages)

        llm_span_id = _new_id()
        llm_span = _build_llm_span(messages, content, tool_calls, usage, llm_span_id, actual_start, agent_name)
        self.current_spans.append(llm_span)
        if tool_calls:
            self.current_spans.extend(_build_tool_spans(tool_calls, llm_span_id, llm_span.end_time))

    def finalize(self) -> None:
        if not self.current_spans:
            return
        now = _now()
        last_llm = next(
            (s for s in reversed(self.current_spans) if s.span_type == SpanType.LLM_CALL),
            None,
        )
        final_output = str(last_llm.output.get("content", "")) if last_llm and last_llm.output else None
        self.traces.append(
            Trace(
                id=_new_id(),
                task=self.current_task,
                agent_name="agentlens-proxy",
                spans=list(self.current_spans),
                final_output=final_output,
                started_at=self.current_spans[0].start_time,
                completed_at=now,
                session_id=self._session_id,
            )
        )
        if self._traces_dir is not None:
            trace = self.traces[-1]
            path = self._traces_dir / f"{trace.id}.json"
            path.write_text(trace.model_dump_json(indent=2))
        self.current_spans.clear()
        self.current_task = "unknown"

    def get_trace(self, trace_id: str) -> Trace | None:
        return next((t for t in self.traces if t.id == trace_id), None)

    def reset(self) -> None:
        self.finalize()
