"""Tests for OTel-compatible JSON export."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from agentlens.export.otel import export_otel_json, export_otel_json_file
from agentlens.models.trace import Span, SpanStatus, SpanType, Trace


def _get_spans(result: dict[str, Any]) -> list[dict[str, Any]]:
    return result["resourceSpans"][0]["scopeSpans"][0]["spans"]  # type: ignore[no-any-return]


def _get_attribute(span: dict[str, Any], key: str) -> Any:
    for attr in span["attributes"]:
        if attr["key"] == key:
            return next(iter(attr["value"].values()))
    return None


# ---------------------------------------------------------------------------
# test_export_otel_json_has_resource_spans
# ---------------------------------------------------------------------------


def test_export_otel_json_has_resource_spans(sample_trace: Trace) -> None:
    # Arrange / Act
    result = export_otel_json(sample_trace)

    # Assert
    assert "resourceSpans" in result
    resource_spans = result["resourceSpans"]
    assert len(resource_spans) == 1
    assert "resource" in resource_spans[0]
    assert "scopeSpans" in resource_spans[0]
    assert len(_get_spans(result)) == len(sample_trace.spans)


# ---------------------------------------------------------------------------
# test_export_otel_span_has_trace_id
# ---------------------------------------------------------------------------


def test_export_otel_span_has_trace_id(sample_trace: Trace) -> None:
    # Arrange / Act
    result = export_otel_json(sample_trace)
    spans = _get_spans(result)

    # Assert — every span carries a 32-char hex trace_id
    for span in spans:
        trace_id: str = span["traceId"]
        assert len(trace_id) == 32
        assert all(c in "0123456789abcdefABCDEF" for c in trace_id)


# ---------------------------------------------------------------------------
# test_export_otel_span_has_attributes
# ---------------------------------------------------------------------------


def test_export_otel_span_has_attributes(sample_trace: Trace) -> None:
    # Arrange / Act
    result = export_otel_json(sample_trace)
    spans = _get_spans(result)

    # Assert — every span has gen_ai.operation.name
    for span in spans:
        assert _get_attribute(span, "gen_ai.operation.name") is not None


# ---------------------------------------------------------------------------
# test_export_otel_llm_call_maps_to_chat
# ---------------------------------------------------------------------------


def test_export_otel_llm_call_maps_to_chat(sample_trace: Trace) -> None:
    # Arrange / Act
    result = export_otel_json(sample_trace)
    spans = _get_spans(result)

    # Assert — first span is LLM_CALL → operation "chat"
    llm_span = spans[0]
    assert _get_attribute(llm_span, "gen_ai.operation.name") == "chat"


# ---------------------------------------------------------------------------
# test_export_otel_tool_call_maps_to_tool
# ---------------------------------------------------------------------------


def test_export_otel_tool_call_maps_to_tool(sample_trace: Trace) -> None:
    # Arrange / Act
    result = export_otel_json(sample_trace)
    spans = _get_spans(result)

    # Assert — second span is TOOL_CALL → operation "tool"
    tool_span = spans[1]
    assert _get_attribute(tool_span, "gen_ai.operation.name") == "tool"


# ---------------------------------------------------------------------------
# test_export_otel_token_usage_in_attributes
# ---------------------------------------------------------------------------


def test_export_otel_token_usage_in_attributes(sample_trace: Trace) -> None:
    # Arrange / Act
    result = export_otel_json(sample_trace)
    spans = _get_spans(result)

    # Assert — first LLM span has token usage attributes
    llm_span = spans[0]
    input_tokens = _get_attribute(llm_span, "gen_ai.usage.input_tokens")
    output_tokens = _get_attribute(llm_span, "gen_ai.usage.output_tokens")
    assert input_tokens == 50
    assert output_tokens == 25


# ---------------------------------------------------------------------------
# test_export_otel_agent_name_in_attributes
# ---------------------------------------------------------------------------


def test_export_otel_agent_name_in_attributes() -> None:
    # Arrange
    base = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    span = Span(
        id="span_agent",
        span_type=SpanType.LLM_CALL,
        name="agent_step",
        input={"messages": []},
        status=SpanStatus.SUCCESS,
        start_time=base,
        end_time=base + timedelta(milliseconds=100),
        metadata={"agent_name": "ML Scientist"},
    )
    trace = Trace(
        id="trace_agent",
        task="Agent task",
        agent_name="research-agent",
        spans=[span],
        started_at=base,
        completed_at=base + timedelta(milliseconds=100),
    )

    # Act
    result = export_otel_json(trace)
    otel_span = _get_spans(result)[0]

    # Assert
    assert _get_attribute(otel_span, "gen_ai.agent.name") == "ML Scientist"


# ---------------------------------------------------------------------------
# test_export_otel_json_file_writes_to_disk
# ---------------------------------------------------------------------------


def test_export_otel_json_file_writes_to_disk(sample_trace: Trace, tmp_path: Path) -> None:
    # Arrange
    output = tmp_path / "otel.json"

    # Act
    export_otel_json_file(sample_trace, output)

    # Assert
    assert output.exists()
    data = json.loads(output.read_text())
    assert "resourceSpans" in data
    assert len(_get_spans(data)) == len(sample_trace.spans)
