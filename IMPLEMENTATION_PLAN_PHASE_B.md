# Phase B: Mailbox Adapter

**Dependencies:** Phase A (TraceCollector must exist in `server/collector.py`)
**Agent:** `python-fastapi`

## Overview

Add a mailbox mode to the proxy server. When `--mode mailbox`, incoming `/v1/chat/completions` requests are queued instead of answered immediately. An external "brain" (Claude Code agent, curl, any HTTP client) polls the queue, reads requests, and submits responses. The proxy unblocks and returns the response to the calling agent. Traces are captured as normal.

## Files to Create

### `src/agentlens/server/mailbox.py`
**Purpose:** Async mailbox queue for human/AI-in-the-loop evaluation
**Classes:**

#### `MailboxEntry(BaseModel)`
- `request_id: int`
- `messages: list[dict[str, Any]]`
- `model: str`
- `tools: list[dict[str, Any]]`
- `timestamp: float` — `time.time()` when queued
- NOT frozen (response is set later via a separate mechanism)

#### `MailboxResponse(BaseModel)`
- `content: str = ""`
- `tool_calls: list[dict[str, Any]] = Field(default_factory=list)`

#### `MailboxQueue`
- `_pending: dict[int, MailboxEntry]` — request_id → entry
- `_events: dict[int, asyncio.Event]` — request_id → event for async wait
- `_responses: dict[int, MailboxResponse]` — request_id → submitted response
- `_counter: int = 0` — auto-incrementing request ID
- `_timeout: float` — default 300.0 seconds
- `_served: int = 0` — total requests served (for stats)

**Methods:**
- `__init__(self, timeout: float = 300.0)`
- `enqueue(self, messages: list[dict[str, Any]], model: str, tools: list[dict[str, Any]]) -> MailboxEntry`
  - Increment counter, create entry, create Event, store in _pending
  - Return entry
- `async wait_for_response(self, request_id: int) -> MailboxResponse`
  - Get the Event for request_id
  - `await asyncio.wait_for(event.wait(), timeout=self._timeout)`
  - On timeout: raise `TimeoutError`
  - On success: pop from _pending/_events, increment _served, return _responses[request_id]
- `submit_response(self, request_id: int, response: MailboxResponse) -> None`
  - Validate request_id exists in _pending, raise ValueError if not
  - Store response in _responses, set the Event
- `list_pending(self) -> list[MailboxEntry]`
  - Return list of pending entries sorted by request_id
- `get_entry(self, request_id: int) -> MailboxEntry | None`
  - Return entry or None
- `stats(self) -> dict[str, Any]`
  - Return `{"pending": len(_pending), "served": _served, "timeout": _timeout}`

**Constraints:**
- Use `asyncio.Event` for blocking/unblocking (stdlib, no new deps)
- Under 120 lines
- No FastAPI imports — this is a pure async data structure

### `tests/test_mailbox.py`
**Purpose:** Test MailboxQueue in isolation
**Tests:**
- `test_enqueue_creates_pending_entry` — Enqueue, verify list_pending returns it
- `test_submit_response_unblocks_waiter` — Enqueue, submit in background, verify wait_for_response returns the response
- `test_wait_timeout_raises` — Enqueue with timeout=0.1, don't submit, verify TimeoutError
- `test_submit_unknown_id_raises` — Submit response for non-existent ID, verify ValueError
- `test_stats_reflects_state` — Enqueue 2, serve 1, check stats counts
- `test_get_entry_returns_none_for_unknown` — get_entry with bad ID returns None
- `test_list_pending_excludes_served` — After submit+wait, entry no longer in list_pending

**Pattern:** Use `pytest-asyncio` for async tests. Mark with `@pytest.mark.asyncio`.
**Fixture strategy for `test_submit_response_unblocks_waiter`:**
```python
async def test_submit_response_unblocks_waiter():
    queue = MailboxQueue(timeout=5.0)
    entry = queue.enqueue([{"role": "user", "content": "hi"}], "test", [])
    task = asyncio.create_task(queue.wait_for_response(entry.request_id))
    await asyncio.sleep(0.01)  # let the waiter start
    queue.submit_response(entry.request_id, MailboxResponse(content="hello"))
    result = await task
    assert result.content == "hello"
```

## Files to Modify

### `src/agentlens/server/proxy.py` (MODIFY)
**Changes:**
1. Import `MailboxQueue`, `MailboxResponse` from `agentlens.server.mailbox`
2. Extend `create_app` signature: `mode: Literal["mock", "proxy", "mailbox"]`, add `timeout: float = 300.0`
3. In `create_app()`, if mode == "mailbox": create `mailbox = MailboxQueue(timeout=timeout)`
4. In `chat_completions` endpoint, add mailbox branch:
   ```python
   elif mode == "mailbox":
       entry = mailbox.enqueue(
           [m.model_dump() for m in request.messages],
           request.model,
           request.tools if request.tools is not None else [],
       )
       try:
           mb_response = await mailbox.wait_for_response(entry.request_id)
       except TimeoutError:
           raise HTTPException(408, "Mailbox request timed out")
       content = mb_response.content
       tool_calls_raw = mb_response.tool_calls
       usage = {"prompt_tokens": 0, "completion_tokens": 0}
       response = _build_openai_response(content, tool_calls_raw, usage, request.model)
   ```
5. Add 4 new mailbox endpoints inside an `if mode == "mailbox":` block within `create_app()`:

   **`GET /mailbox`** → `async def list_mailbox() -> list[dict[str, Any]]`
   Returns list of pending entries, each as:
   ```json
   {"request_id": 1, "model": "gpt-4o-mini", "preview": "Research the GDP of...", "age_seconds": 2.3}
   ```
   - `preview` = first 100 chars of last user message content
   - `age_seconds` = `time.time() - entry.timestamp`

   **`GET /mailbox/{request_id}`** → `async def get_mailbox_entry(request_id: int) -> dict[str, Any]`
   Returns full entry details:
   ```json
   {
     "request_id": 1,
     "model": "gpt-4o-mini",
     "messages": [...],
     "tools": [...],
     "response_hint": {
       "format": "plain text or JSON with tool_calls",
       "example_text": {"response": "Your answer here"},
       "example_tool_call": {"content": "", "tool_calls": [{"id": "call_001", "type": "function", "function": {"name": "search", "arguments": "{}"}}]}
     },
     "age_seconds": 2.3
   }
   ```
   Raise `HTTPException(404)` if request_id not found.

   **`POST /mailbox/{request_id}`** → `async def submit_mailbox_response(request_id: int, body: dict[str, Any]) -> dict[str, str]`
   Accepts two formats:
   - Simple: `{"response": "text"}` → `MailboxResponse(content="text")`
   - Structured: `{"content": "...", "tool_calls": [...]}` → `MailboxResponse(content=..., tool_calls=...)`
   Detection: if `"response"` key exists, use simple format; otherwise use structured.
   Returns `{"status": "submitted"}`.
   Raise `HTTPException(404)` if request_id not found (catch `ValueError` from `submit_response`).

   **`GET /mailbox/stats`** → `async def mailbox_stats() -> dict[str, Any]`
   Returns `mailbox.stats()` directly.

6. Extract helper (keep `_canned_to_response` as-is for mock path, add new helper for mailbox/general use):
   ```python
   def _build_openai_response(
       content: str,
       tool_calls: list[dict[str, Any]],
       usage: dict[str, int],
       model: str,
   ) -> ChatCompletionResponse:
   ```
   Builds a `ChatCompletionResponse` from raw content/tool_calls/usage. Used by the mailbox branch. The mock branch keeps using `_canned_to_response` (which takes a `CannedResponse` object).

**Response format for POST /mailbox/{request_id}:**
Accept two formats:
- Simple: `{"response": "text here"}` → convert to `MailboxResponse(content="text here")`
- Structured: `{"content": "...", "tool_calls": [...]}` → convert to `MailboxResponse(content=..., tool_calls=...)`

### `src/agentlens/cli.py` (MODIFY)
**Changes:**
1. Update `serve` command:
   - Change mode help text: `"Server mode: mock|proxy|mailbox"`
   - Add `--timeout` / `-t` option: `float = 300.0`, help="Mailbox request timeout in seconds"
   - Update `server_mode` logic: `Literal["mock", "proxy", "mailbox"]`
   - Pass `timeout` to `create_app()`

## Verification

```bash
# Existing tests still pass
uv run pytest tests/test_server.py -v

# New mailbox tests pass
uv run pytest tests/test_mailbox.py -v

# Manual smoke test:
# Terminal 1:
uv run agentlens serve --mode mailbox
# Terminal 2:
curl -s http://localhost:8650/mailbox | python -m json.tool  # empty pending
curl -s -X POST http://localhost:8650/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"test","messages":[{"role":"user","content":"hello"}]}' &
# Terminal 2 (while curl blocks):
curl -s http://localhost:8650/mailbox | python -m json.tool  # shows pending request
curl -s -X POST http://localhost:8650/mailbox/1 \
  -H "Content-Type: application/json" \
  -d '{"response":"world"}'
# The blocked curl should return with "world" in the response
```
