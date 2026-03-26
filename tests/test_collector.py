"""Unit tests for TraceCollector."""

from __future__ import annotations

from agentlens.models.trace import SpanType
from agentlens.server.collector import TraceCollector
from agentlens.server.models import ChatMessage


def _make_messages(user_content: str = "hello") -> list[ChatMessage]:
    return [ChatMessage(role="user", content=user_content)]


def _make_usage(prompt: int = 10, completion: int = 5) -> dict[str, int]:
    return {"prompt_tokens": prompt, "completion_tokens": completion}


# ---------------------------------------------------------------------------
# record_llm_call
# ---------------------------------------------------------------------------


def test_record_llm_call_adds_span() -> None:
    # Arrange
    collector = TraceCollector()

    # Act
    collector.record_llm_call(_make_messages(), "response text", [], _make_usage())

    # Assert
    assert len(collector.current_spans) == 1
    assert collector.current_spans[0].span_type == SpanType.LLM_CALL


def test_record_llm_call_with_tool_calls_adds_child_spans() -> None:
    # Arrange
    collector = TraceCollector()
    tool_calls = [{"function": {"name": "search", "arguments": '{"q": "test"}'}}]

    # Act
    collector.record_llm_call(_make_messages(), "", tool_calls, _make_usage())

    # Assert
    assert len(collector.current_spans) == 2
    llm_span = collector.current_spans[0]
    tool_span = collector.current_spans[1]
    assert llm_span.span_type == SpanType.LLM_CALL
    assert tool_span.span_type == SpanType.TOOL_CALL
    assert tool_span.parent_id == llm_span.id


def test_current_task_set_from_first_message() -> None:
    # Arrange
    collector = TraceCollector()

    # Act
    collector.record_llm_call(_make_messages("my task content"), "response", [], _make_usage())

    # Assert
    assert collector.current_task == "my task content"


# ---------------------------------------------------------------------------
# finalize
# ---------------------------------------------------------------------------


def test_finalize_creates_trace() -> None:
    # Arrange
    collector = TraceCollector()
    collector.record_llm_call(_make_messages(), "the answer", [], _make_usage())

    # Act
    collector.finalize()

    # Assert
    assert len(collector.traces) == 1
    assert len(collector.traces[0].spans) == 1


def test_finalize_empty_does_nothing() -> None:
    # Arrange
    collector = TraceCollector()

    # Act
    collector.finalize()

    # Assert
    assert collector.traces == []


def test_finalize_clears_current_spans() -> None:
    # Arrange
    collector = TraceCollector()
    collector.record_llm_call(_make_messages(), "response", [], _make_usage())

    # Act
    collector.finalize()

    # Assert
    assert collector.current_spans == []
    assert collector.current_task == "unknown"


# ---------------------------------------------------------------------------
# reset
# ---------------------------------------------------------------------------


def test_reset_finalizes_and_clears() -> None:
    # Arrange
    collector = TraceCollector()
    collector.record_llm_call(_make_messages(), "response", [], _make_usage())

    # Act
    collector.reset()

    # Assert
    assert len(collector.traces) == 1
    assert collector.current_spans == []


# ---------------------------------------------------------------------------
# get_trace
# ---------------------------------------------------------------------------


def test_get_trace_by_id() -> None:
    # Arrange
    collector = TraceCollector()
    collector.record_llm_call(_make_messages(), "response", [], _make_usage())
    collector.finalize()
    trace_id = collector.traces[0].id

    # Act
    result = collector.get_trace(trace_id)

    # Assert
    assert result is not None
    assert result.id == trace_id


def test_get_trace_unknown_returns_none() -> None:
    # Arrange
    collector = TraceCollector()

    # Act
    result = collector.get_trace("nonexistent-id")

    # Assert
    assert result is None
