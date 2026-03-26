# Phase A: Refactor — Extract Trace Collector

**Dependencies:** None
**Agent:** `python-fastapi`

## Overview

Extract the span-building and trace-finalization logic from `proxy.py` into a reusable `TraceCollector` class. This gives both the existing OpenAI endpoint and the future mailbox adapter a shared mechanism for emitting spans, without duplicating code.

**Key constraint:** After this refactor, ALL existing tests must still pass and behavior must be identical.

## Files to Create

### `src/agentlens/server/collector.py`
**Purpose:** Shared trace collection logic — builds spans, accumulates them, finalizes traces
**Classes:**

#### `TraceCollector`
- `__init__(self)` — Initialize empty state
- `traces: list[Trace]` — Completed traces (public, read by /traces endpoints)
- `current_spans: list[Span]` — Spans being accumulated
- `current_task: str` — Task description (from first user message)

**Methods:**
- `record_llm_call(self, messages: list[ChatMessage], content: str, tool_calls: list[dict[str, Any]], usage: dict[str, int]) -> None`
  - Creates an LLM_CALL span + TOOL_CALL child spans (if tool_calls present)
  - Appends to `current_spans`
  - Sets `current_task` from first user message if no spans yet
  - Uses the existing `_build_llm_span` and `_build_tool_spans` helper logic (move them here as private methods)

- `finalize(self) -> None`
  - If `current_spans` is non-empty, builds a `Trace` and appends to `traces`
  - Clears `current_spans` and resets `current_task`
  - Uses existing `_finalize_trace` logic

- `get_trace(self, trace_id: str) -> Trace | None`
  - Find trace by ID in `traces`

- `reset(self) -> None`
  - Calls `finalize()` then keeps `traces` intact
  - (Same as current `/traces/reset` behavior)

**Private helpers (moved from proxy.py):**
- `_new_id() -> str` — `uuid.uuid4().hex[:12]`
- `_now() -> datetime` — `datetime.now(UTC)`
- `_build_llm_span(...)` — Same as current proxy.py
- `_build_tool_spans(...)` — Same as current proxy.py

**Constraints:**
- Import `ChatMessage` from `server.models` for type annotation
- Under 120 lines
- No FastAPI imports — this is a pure data class, not an endpoint
**Reference:** Current `src/agentlens/server/proxy.py` lines 23-125 (the functions being moved: `_new_id`, `_now`, `_build_llm_span`, `_build_tool_spans`, `_finalize_trace`)

### `tests/test_collector.py`
**Purpose:** Test TraceCollector in isolation
**Tests:**
- `test_record_llm_call_adds_span` — Record one call, verify current_spans has LLM_CALL span
- `test_record_llm_call_with_tool_calls_adds_child_spans` — Verify TOOL_CALL spans created with parent_id
- `test_finalize_creates_trace` — Record calls, finalize, verify trace in `traces` list
- `test_finalize_empty_does_nothing` — Finalize with no spans, traces stays empty
- `test_reset_finalizes_and_clears` — Record, reset, verify trace created and current_spans empty
- `test_get_trace_by_id` — Finalize, then get_trace returns the trace
- `test_get_trace_unknown_returns_none` — get_trace with bad ID returns None
- `test_current_task_set_from_first_message` — First call sets current_task from user message

**Fixtures:** Create `ChatMessage` objects inline (they're simple Pydantic models)

## Files to Modify

### `src/agentlens/server/proxy.py` (MODIFY)
**Changes:**
1. Remove `_new_id`, `_now`, `_build_llm_span`, `_build_tool_spans`, `_finalize_trace` — they move to `collector.py`
2. Import `TraceCollector` from `agentlens.server.collector`
3. In `create_app()`:
   - Replace `traces`, `current_spans`, `current_task` closure variables with a single `collector = TraceCollector()`
   - In `chat_completions`: replace manual span building with `collector.record_llm_call(request.messages, content, tool_calls_raw, usage)`
   - In `list_traces`: use `collector.traces`
   - In `get_trace`: use `collector.get_trace(trace_id)`
   - In `reset_traces`: call `collector.reset()`
   - In `switch_scenario`: call `collector.reset()`
4. Keep `_canned_to_response` and `_proxy_request` in proxy.py (they're OpenAI-specific)
5. `create_app` signature stays the same: `mode: Literal["mock", "proxy"]`

**Result:** proxy.py should shrink from 247 to ~150 lines. All behavior unchanged.

### `tests/test_server.py` (MODIFY — minimal)
**Changes:** None expected — all tests should pass unchanged since the API behavior is identical. If any test directly tested internal functions (they don't), adjust imports.

## Verification

```bash
uv run pytest tests/test_server.py tests/test_collector.py -v  # All pass
uv run pytest tests/ -v                                         # Full suite green
uv run ruff check src/ tests/
uv run pyright src/
```
