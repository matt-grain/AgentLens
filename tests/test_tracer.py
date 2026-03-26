from __future__ import annotations

import pytest

from agentlens.capture.tracer import Tracer
from agentlens.models.trace import SpanStatus, SpanType, TokenUsage


def test_tracer_creates_trace_with_task_and_agent() -> None:
    with Tracer(task="search for info", agent_name="research-agent") as tracer:
        pass
    trace = tracer.get_trace()
    assert trace.task == "search for info"
    assert trace.agent_name == "research-agent"


def test_tracer_records_timestamps() -> None:
    with Tracer(task="task", agent_name="agent") as tracer:
        pass
    trace = tracer.get_trace()
    assert trace.started_at is not None
    assert trace.completed_at is not None
    assert trace.completed_at >= trace.started_at


def test_tracer_add_span_appends_to_trace() -> None:
    with Tracer(task="task", agent_name="agent") as tracer:
        tracer.add_span(SpanType.LLM_CALL, "call1", {"prompt": "hello"}, output={"content": "hi"})
        tracer.add_span(SpanType.TOOL_CALL, "search", {"query": "x"}, output={"result": "y"})
    trace = tracer.get_trace()
    assert len(trace.spans) == 2
    assert trace.spans[0].name == "call1"
    assert trace.spans[1].name == "search"


def test_tracer_start_span_and_complete() -> None:
    with Tracer(task="task", agent_name="agent") as tracer:
        builder = tracer.start_span(SpanType.TOOL_CALL, "fetch", {"url": "http://example.com"})
        span = builder.complete(output={"result": "page content"})
    trace = tracer.get_trace()
    assert len(trace.spans) == 1
    assert trace.spans[0].id == span.id
    assert trace.spans[0].output == {"result": "page content"}
    assert span.duration_ms >= 0


def test_tracer_generates_unique_ids() -> None:
    ids: list[str] = []
    for _ in range(3):
        with Tracer(task="task", agent_name="agent") as tracer:
            tracer.add_span(SpanType.LLM_CALL, "call", {"x": 1}, output={"content": "y"})
            ids.append(tracer.trace_id)
        trace = tracer.get_trace()
        ids.extend(s.id for s in trace.spans)
    assert len(ids) == len(set(ids)), "All trace and span IDs must be unique"


def test_tracer_context_manager_usage() -> None:
    with Tracer(task="full test", agent_name="test-agent") as tracer:
        tracer.add_span(
            SpanType.LLM_CALL,
            "plan",
            {"messages": [{"role": "user", "content": "help"}]},
            output={"content": "sure"},
            token_usage=TokenUsage(input_tokens=10, output_tokens=5),
        )
    trace = tracer.get_trace()
    assert trace.id == tracer.trace_id
    assert len(trace.spans) == 1
    assert trace.total_tokens is not None
    assert trace.total_tokens.input_tokens == 10


def test_tracer_get_trace_before_exit_raises() -> None:
    tracer = Tracer(task="task", agent_name="agent")
    tracer.__enter__()
    with pytest.raises(RuntimeError):
        tracer.get_trace()
    tracer.__exit__(None, None, None)


def test_tracer_start_span_records_parent_id() -> None:
    with Tracer(task="task", agent_name="agent") as tracer:
        parent = tracer.add_span(SpanType.LLM_CALL, "parent", {"x": 1}, output={"content": "y"})
        child_builder = tracer.start_span(SpanType.TOOL_CALL, "child", {"q": "test"}, parent_id=parent.id)
        child = child_builder.complete(output={"result": "found"}, status=SpanStatus.SUCCESS)
    assert child.parent_id == parent.id
