# Phase P2.3: OTel-Compatible Export

**Dependencies:** None (works with existing Trace model; benefits from P2.1 RAG spans and P2.2 session_id if present but doesn't require them)
**Agent:** `python-fastapi`

## Overview

Add an export module that maps AgentLens Trace/Span to OpenTelemetry GenAI semantic conventions as JSON. This shows production observability awareness and enables interop with Jaeger, Grafana Tempo, and Datadog. Start with JSON export only (no gRPC dependency).

## OTel GenAI Semantic Conventions Reference

The mapping follows the [OTel GenAI conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/):

| AgentLens Field | OTel Attribute |
|----------------|----------------|
| `Span.span_type == LLM_CALL` | `gen_ai.operation.name = "chat"` |
| `Span.span_type == TOOL_CALL` | `gen_ai.operation.name = "tool"` |
| `Span.span_type == RETRIEVAL` | `gen_ai.operation.name = "retrieval"` |
| `Span.span_type == EMBEDDING` | `gen_ai.operation.name = "embedding"` |
| `Span.name` | `name` (OTel span name) |
| `Span.id` | `span_id` (hex) |
| `Span.parent_id` | `parent_span_id` (hex) |
| `Trace.id` | `trace_id` (hex, padded to 32 chars) |
| `Span.start_time` | `start_time_unix_nano` |
| `Span.end_time` | `end_time_unix_nano` |
| `Span.token_usage.input_tokens` | `gen_ai.usage.input_tokens` |
| `Span.token_usage.output_tokens` | `gen_ai.usage.output_tokens` |
| `Span.metadata.agent_name` | `gen_ai.agent.name` |
| `Trace.session_id` | `gen_ai.conversation.id` |
| `Span.status` | `status.code` (OK/ERROR) |

## Files to Create

### `src/agentlens/export/__init__.py` (CREATE)
```python
"""Trace export in standard formats."""

from agentlens.export.otel import export_otel_json

__all__ = ["export_otel_json"]
```

### `src/agentlens/export/otel.py` (CREATE)
**Purpose:** Map AgentLens Trace to OTel JSON format
**Functions:**

#### `export_otel_json(trace: Trace) -> dict[str, Any]`
Returns OTel-compatible JSON structure:
```json
{
  "resourceSpans": [{
    "resource": {
      "attributes": [
        {"key": "service.name", "value": {"stringValue": "agentlens"}},
        {"key": "service.version", "value": {"stringValue": "0.1.0"}}
      ]
    },
    "scopeSpans": [{
      "scope": {"name": "agentlens", "version": "0.1.0"},
      "spans": [...]
    }]
  }]
}
```

#### `_map_span(span: Span, trace_id: str, session_id: str | None = None) -> dict[str, Any]`
Note: `session_id` comes from `Trace` (not `Span`). The caller `export_otel_json` passes `getattr(trace, 'session_id', None)` — this works whether P2.2 has been implemented or not. If `session_id` is not None, add `gen_ai.conversation.id` attribute.
Maps a single AgentLens Span to OTel span format:
```json
{
  "traceId": "00000000000000008a3d71f15eb3xxxx",
  "spanId": "a1b2c3d4e5f6",
  "parentSpanId": "...",
  "name": "llm_call",
  "kind": 3,
  "startTimeUnixNano": 1711440000000000000,
  "endTimeUnixNano":   1711440000500000000,
  "status": {"code": 1},
  "attributes": [
    {"key": "gen_ai.operation.name", "value": {"stringValue": "chat"}},
    {"key": "gen_ai.usage.input_tokens", "value": {"intValue": 50}},
    {"key": "gen_ai.usage.output_tokens", "value": {"intValue": 30}},
    {"key": "gen_ai.agent.name", "value": {"stringValue": "ML Scientist"}}
  ]
}
```

#### `_span_type_to_operation(span_type: SpanType) -> str`
Map known types: LLM_CALL→"chat", TOOL_CALL→"tool", DECISION→"decision", ERROR→"error", ESCALATION→"escalation". For any other type (including RETRIEVAL and EMBEDDING if P2.1 was implemented), use `span_type.value` as the operation name. This makes the export forward-compatible — no need to hardcode every SpanType variant.

#### `_datetime_to_unix_nano(dt: datetime) -> int`
Convert datetime to nanosecond Unix timestamp.

#### `export_otel_json_file(trace: Trace, output_path: Path) -> None`
Convenience: calls `export_otel_json` and writes to file with `json.dumps(indent=2)`.

**Constraints:**
- Under 120 lines
- No external OTel dependencies (pure JSON mapping)
- Import only from `agentlens.models.*` and stdlib
- trace_id padded to 32 hex chars (OTel requires it)
- span_id padded to 16 hex chars

## Files to Modify

### `src/agentlens/cli.py` (MODIFY)
**Changes:**
Add `export-otel` command:
```python
@app.command("export-otel")
def export_otel(
    trace_file: Annotated[Path, typer.Argument(help="Path to trace JSON file")],
    output: Annotated[Path, typer.Option("--output", "-o", help="Output path")] = Path("trace_otel.json"),
) -> None:
    """Export a trace in OpenTelemetry JSON format."""
    from agentlens.export.otel import export_otel_json_file
    from agentlens.models.trace import Trace

    trace = Trace.model_validate_json(trace_file.read_text())
    export_otel_json_file(trace, output)
    typer.echo(f"OTel JSON written to {output}")
```

## Test File

### `tests/test_otel_export.py` (CREATE)
**Tests:**
- `test_export_otel_json_has_resource_spans` — Export sample trace, verify top-level structure
- `test_export_otel_span_has_trace_id` — Verify traceId is 32 hex chars
- `test_export_otel_span_has_attributes` — Verify gen_ai.operation.name present
- `test_export_otel_llm_call_maps_to_chat` — LLM_CALL → "chat"
- `test_export_otel_tool_call_maps_to_tool` — TOOL_CALL → "tool"
- `test_export_otel_token_usage_in_attributes` — Verify gen_ai.usage.input_tokens
- `test_export_otel_agent_name_in_attributes` — Span with metadata.agent_name → gen_ai.agent.name
- `test_export_otel_json_file_writes_to_disk` — tmp_path, verify file content is valid JSON

**Fixture strategy:** Use `sample_trace` from conftest.py.

## Verification

```bash
uv run pytest tests/test_otel_export.py -v
uv run agentlens export-otel demo/fixtures/happy_path.json -o /tmp/otel.json
python -c "import json; d=json.load(open('/tmp/otel.json')); print(len(d['resourceSpans'][0]['scopeSpans'][0]['spans']), 'spans')"
```
