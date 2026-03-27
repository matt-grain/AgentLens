"""OTel-compatible JSON export for AgentLens traces.

Maps AgentLens Trace/Span to OpenTelemetry GenAI semantic conventions.
No external OTel dependencies — pure JSON mapping.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Final

from agentlens.models.trace import Span, SpanStatus, SpanType, Trace

_SERVICE_NAME: Final[str] = "agentlens"
_SERVICE_VERSION: Final[str] = "0.1.0"

# OTel status codes: 0=UNSET, 1=OK, 2=ERROR
_STATUS_OK: Final[int] = 1
_STATUS_ERROR: Final[int] = 2

# OTel span kind: 3=CLIENT
_SPAN_KIND_CLIENT: Final[int] = 3

_KNOWN_OPERATIONS: Final[dict[SpanType, str]] = {
    SpanType.LLM_CALL: "chat",
    SpanType.TOOL_CALL: "tool",
    SpanType.DECISION: "decision",
    SpanType.ERROR: "error",
    SpanType.ESCALATION: "escalation",
}


def _id_to_hex(raw_id: str, length: int) -> str:
    """Return a deterministic hex string of `length` chars from an arbitrary ID.

    Pass-through when the ID is already valid hex of the right length; otherwise
    derive from an MD5 digest (covers human-readable IDs such as "trace001").
    """
    hex_chars = set("0123456789abcdefABCDEF")
    if len(raw_id) == length and all(c in hex_chars for c in raw_id):
        return raw_id
    digest = hashlib.md5(raw_id.encode(), usedforsecurity=False).hexdigest()  # noqa: S324
    # MD5 yields 32 hex chars — pad by repeating then slice to `length`
    return (digest * 2)[:length]


def _datetime_to_unix_nano(dt: datetime) -> int:
    """Convert a datetime to nanosecond Unix timestamp."""
    return int(dt.timestamp() * 1_000_000_000)


def _span_type_to_operation(span_type: SpanType) -> str:
    """Map SpanType to OTel gen_ai.operation.name; falls back to the enum value."""
    return _KNOWN_OPERATIONS.get(span_type, span_type.value)


def _attr(key: str, value: str | int) -> dict[str, Any]:
    if isinstance(value, int):
        return {"key": key, "value": {"intValue": value}}
    return {"key": key, "value": {"stringValue": value}}


def _map_span(span: Span, trace_id: str, session_id: str | None = None) -> dict[str, Any]:
    """Map a single AgentLens Span to an OTel span dict."""
    attributes: list[dict[str, Any]] = [
        _attr("gen_ai.operation.name", _span_type_to_operation(span.span_type)),
    ]

    if span.token_usage is not None:
        attributes.append(_attr("gen_ai.usage.input_tokens", span.token_usage.input_tokens))
        attributes.append(_attr("gen_ai.usage.output_tokens", span.token_usage.output_tokens))

    agent_name: str | None = span.metadata.get("agent_name")
    if agent_name is not None:
        attributes.append(_attr("gen_ai.agent.name", agent_name))

    if session_id is not None:
        attributes.append(_attr("gen_ai.conversation.id", session_id))

    status_code = _STATUS_ERROR if span.status == SpanStatus.FAILURE else _STATUS_OK

    otel_span: dict[str, Any] = {
        "traceId": trace_id,
        "spanId": _id_to_hex(span.id, 16),
        "name": span.name,
        "kind": _SPAN_KIND_CLIENT,
        "startTimeUnixNano": _datetime_to_unix_nano(span.start_time),
        "endTimeUnixNano": _datetime_to_unix_nano(span.end_time),
        "status": {"code": status_code},
        "attributes": attributes,
    }

    if span.parent_id is not None:
        otel_span["parentSpanId"] = _id_to_hex(span.parent_id, 16)

    return otel_span


def export_otel_json(trace: Trace) -> dict[str, Any]:
    """Export an AgentLens Trace as an OTel resourceSpans JSON structure."""
    trace_id = _id_to_hex(trace.id, 32)
    session_id: str | None = getattr(trace, "session_id", None)

    spans = [_map_span(span, trace_id, session_id) for span in trace.spans]

    return {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        _attr("service.name", _SERVICE_NAME),
                        _attr("service.version", _SERVICE_VERSION),
                    ]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": _SERVICE_NAME, "version": _SERVICE_VERSION},
                        "spans": spans,
                    }
                ],
            }
        ]
    }


def export_otel_json_file(trace: Trace, output_path: Path) -> None:
    """Write OTel JSON export of a trace to a file."""
    data = export_otel_json(trace)
    output_path.write_text(json.dumps(data, indent=2))
