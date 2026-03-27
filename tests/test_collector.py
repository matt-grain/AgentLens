"""Unit tests for TraceCollector."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from agentlens.models.trace import SpanType, Trace
from agentlens.server.collector import TraceCollector
from agentlens.server.models import ChatMessage, MessageRole


def _make_messages(user_content: str = "hello") -> list[ChatMessage]:
    return [ChatMessage(role=MessageRole.USER, content=user_content)]


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


# ---------------------------------------------------------------------------
# traces_dir persistence
# ---------------------------------------------------------------------------


def test_finalize_saves_trace_to_disk(tmp_path: Path) -> None:
    # Arrange
    collector = TraceCollector(traces_dir=tmp_path)
    collector.record_llm_call(_make_messages("save this"), "saved response", [], _make_usage())

    # Act
    collector.finalize()

    # Assert
    json_files = list(tmp_path.glob("*.json"))
    assert len(json_files) == 1
    trace = Trace.model_validate_json(json_files[0].read_text())
    assert trace.id == collector.traces[0].id
    assert trace.task == "save this"


def test_finalize_without_traces_dir_does_not_save(tmp_path: Path) -> None:
    # Arrange
    collector = TraceCollector(traces_dir=None)
    collector.record_llm_call(_make_messages(), "response", [], _make_usage())

    # Act
    collector.finalize()

    # Assert
    assert list(tmp_path.glob("*.json")) == []


# ---------------------------------------------------------------------------
# start_time and agent identity
# ---------------------------------------------------------------------------


def test_record_llm_call_with_start_time_sets_duration() -> None:
    # Arrange
    collector = TraceCollector()
    start = datetime.now(UTC) - timedelta(milliseconds=500)

    # Act
    collector.record_llm_call(_make_messages(), "response", [], _make_usage(), start_time=start)

    # Assert
    span = collector.current_spans[0]
    assert span.duration_ms > 0


def test_record_llm_call_extracts_agent_name_from_system_message() -> None:
    # Arrange
    collector = TraceCollector()
    messages = [
        ChatMessage(role=MessageRole.SYSTEM, content="You are Research Analyst. You investigate topics thoroughly."),
        ChatMessage(role=MessageRole.USER, content="hello"),
    ]

    # Act
    collector.record_llm_call(messages, "response", [], _make_usage())

    # Assert
    span = collector.current_spans[0]
    assert span.metadata.get("agent_name") == "Research Analyst"


def test_record_llm_call_no_system_message_no_agent_name() -> None:
    # Arrange
    collector = TraceCollector()

    # Act
    collector.record_llm_call(_make_messages(), "response", [], _make_usage())

    # Assert
    span = collector.current_spans[0]
    assert "agent_name" not in span.metadata


# ---------------------------------------------------------------------------
# session_id
# ---------------------------------------------------------------------------


def test_finalize_includes_session_id() -> None:
    # Arrange
    collector = TraceCollector(session_id="sess-1")
    collector.record_llm_call(_make_messages(), "response", [], _make_usage())

    # Act
    collector.finalize()

    # Assert
    assert collector.traces[0].session_id == "sess-1"


def test_finalize_without_session_id_is_none() -> None:
    # Arrange
    collector = TraceCollector()
    collector.record_llm_call(_make_messages(), "response", [], _make_usage())

    # Act
    collector.finalize()

    # Assert
    assert collector.traces[0].session_id is None


def test_set_session_id_updates_next_trace() -> None:
    # Arrange
    collector = TraceCollector()
    collector.record_llm_call(_make_messages(), "response", [], _make_usage())

    # Act
    collector.set_session_id("sess-2")
    collector.finalize()

    # Assert
    assert collector.traces[0].session_id == "sess-2"
