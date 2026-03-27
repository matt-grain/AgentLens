# Phase P2.2: Session/Conversation Grouping

**Dependencies:** None
**Agent:** `python-fastapi`

## Overview

Add `session_id` to Trace so multi-turn agent interactions can be grouped. The proxy accepts a `X-AgentLens-Session` header to tag traces. The CLI `evaluate` command gains a `--session` filter. Minimal changes, high portfolio signal.

## Files to Modify

### `src/agentlens/models/trace.py` (MODIFY)
**Changes:**
1. Add `session_id: str | None = None` field to `Trace`:
   ```python
   class Trace(BaseModel):
       id: str
       task: str
       agent_name: str
       spans: list[Span]
       final_output: str | None = None
       started_at: datetime
       completed_at: datetime
       session_id: str | None = None  # NEW — groups multi-turn traces
   ```

### `src/agentlens/server/collector.py` (MODIFY)
**Changes:**
1. Add `session_id: str | None = None` to `TraceCollector.__init__`:
   ```python
   def __init__(self, traces_dir: Path | None = None, session_id: str | None = None) -> None:
       ...
       self._session_id = session_id
   ```
2. In `finalize()`, pass `session_id=self._session_id` when creating the Trace.
3. Add method `set_session_id(self, session_id: str) -> None` so the proxy can update it per-request.

### `src/agentlens/server/proxy.py` (MODIFY)
**Changes:**
1. In `chat_completions`, read the session header from the request:
   ```python
   from fastapi import Request
   ```
   Add `request_obj: Request` parameter to `chat_completions` (FastAPI injects it):
   ```python
   async def chat_completions(request: ChatCompletionRequest, request_obj: Request) -> dict[str, Any]:
       session_id = request_obj.headers.get("x-agentlens-session")
       if session_id:
           collector.set_session_id(session_id)
   ```
   Note: FastAPI allows both Pydantic body model AND `Request` object in the same handler via DI.

2. In `create_app`, accept optional `session_id: str | None = None` param and pass to `TraceCollector`:
   ```python
   collector = TraceCollector(traces_dir=traces_dir, session_id=session_id)
   ```

### `src/agentlens/cli.py` (MODIFY)
**Changes:**
1. Add `--session` option to `serve` command:
   ```python
   session_id: Annotated[str | None, typer.Option("--session", help="Default session ID for traces")] = None,
   ```
   Pass to `create_app(session_id=session_id, ...)`.

2. Add `--session` filter to `evaluate` command — when evaluating a trace file, show session_id in the header if present. No filtering logic needed (traces are individual files).

## Test Updates

### `tests/test_collector.py` (MODIFY)
**Add tests:**
- `test_finalize_includes_session_id` — Create collector with session_id="sess-1", finalize, verify trace.session_id == "sess-1"
- `test_finalize_without_session_id_is_none` — Default collector, verify trace.session_id is None
- `test_set_session_id_updates_next_trace` — Create collector, call set_session_id("sess-2"), finalize, verify

**Fixture strategy:** Use existing `_make_messages` and `_make_usage` helpers.

## Verification

```bash
uv run pytest tests/test_collector.py -v
uv run pytest tests/ -v
uv run pyright src/
# Manual: curl with header
# curl -H "X-AgentLens-Session: my-session" -X POST http://localhost:8650/v1/chat/completions ...
```
