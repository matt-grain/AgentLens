# Phase 2: Observability Server

**Dependencies:** Phase 1 (models/trace.py)
**Agent:** `python-fastapi`

## Overview

Build the OpenAI-compatible proxy server that captures traces from all LLM calls. Two modes: mock (canned responses) and proxy (forward to real provider).

## Files to Create

### `src/agentlens/server/__init__.py`
**Purpose:** Server subpackage init
**Content:**
```python
"""OpenAI-compatible proxy server for trace capture."""

from agentlens.server.proxy import create_app

__all__ = ["create_app"]
```

### `src/agentlens/server/canned.py`
**Purpose:** Canned responses for mock mode demo scenarios
**Classes:**
- `CannedResponse(BaseModel, frozen=True)`
  - content: str
  - tool_calls: list[dict[str, Any]] = Field(default_factory=list)  — Use plain dicts here (not ToolCall model) because these are serialized directly into OpenAI-compatible JSON responses. Format: `{"id": "call_xxx", "type": "function", "function": {"name": "...", "arguments": "..."}}`
  - usage: dict[str, int] = Field(default_factory=lambda: {"prompt_tokens": 100, "completion_tokens": 50})
- `CannedRegistry` — Singleton registry for scenario responses
  - `responses: dict[str, list[CannedResponse]]` — scenario_name -> ordered responses
  - `_index: dict[str, int]` — tracks position in each scenario
  - `register(scenario: str, responses: list[CannedResponse])` — Add scenario
  - `next_response(scenario: str) -> CannedResponse` — Get next response, cycles if exhausted
  - `reset(scenario: str | None = None)` — Reset index for scenario(s)
**Built-in scenarios to register:**
- `"happy_path"` — 4 responses: plan, search France, search Germany, synthesize
- `"loop"` — 5 responses: plan, search (repeated 3x with same query), finally answer
- `"risk"` — 3 responses: plan with send_email tool call, hallucinated stat, answer
**Constraints:**
- Each response in happy_path should include appropriate tool_calls list
- Tool calls format: `{"id": "call_xxx", "type": "function", "function": {"name": "search", "arguments": "{...}"}}`
- Use module-level `REGISTRY = CannedRegistry()` singleton

### `src/agentlens/server/proxy.py`
**Purpose:** FastAPI app with OpenAI-compatible endpoints
**Functions:**
- `create_app(mode: Literal["mock", "proxy"] = "mock", proxy_target: str | None = None, scenario: str = "happy_path") -> FastAPI`
**Endpoints:**
- `GET /health` → `{"status": "ok", "mode": mode}`
- `GET /v1/models` → OpenAI-compatible model list (single model: "agentlens-mock")
- `POST /v1/chat/completions` → Main endpoint
  - In mock mode: return canned response from registry
  - In proxy mode: forward to proxy_target, capture response
  - Both modes: create Span and add to current trace
- `GET /traces` → List all captured traces as JSON
- `GET /traces/{trace_id}` → Get specific trace
- `POST /traces/reset` → Clear all captured traces
- `POST /scenario/{name}` → Switch active scenario (mock mode only)
**Internal state:**
- `_traces: list[Trace]` — Completed traces
- `_current_spans: list[Span]` — Spans being accumulated for the active trace
- `_current_task: str` — Task description for the active trace (set from first user message)
**Trace lifecycle:**
- A new trace starts on the first `/v1/chat/completions` request (or after a reset)
- Each `/v1/chat/completions` call adds span(s) to `_current_spans`
- `POST /traces/reset` finalizes the current trace (builds `Trace` from accumulated spans, appends to `_traces`, clears `_current_spans`)
- `POST /scenario/{name}` also finalizes and resets
- `GET /traces` returns `_traces` (completed traces only)
- No thread lock needed — FastAPI with uvicorn runs async in a single event loop
**Request/Response models:**
- `ChatCompletionRequest(BaseModel)` — messages, model, tools, etc.
- `ChatCompletionResponse(BaseModel)` — OpenAI-compatible response format
**Constraints:**
- Use `httpx.AsyncClient` for proxy mode forwarding
- Create new Trace on first request if none exists
- Each /v1/chat/completions call creates one LLM_CALL span
- If response contains tool_calls, also create TOOL_CALL spans
- Parse token usage from response into TokenUsage model
- Return proper OpenAI-compatible JSON structure

### `tests/test_server.py`
**Purpose:** Test proxy server functionality
**Tests:**
- `test_health_endpoint_returns_ok` — Basic health check
- `test_models_endpoint_returns_model_list` — /v1/models works
- `test_chat_completions_mock_mode_returns_canned` — Mock response returned
- `test_chat_completions_creates_span` — Span captured in trace
- `test_chat_completions_with_tool_calls_creates_tool_spans` — Tool spans created
- `test_traces_endpoint_returns_captured_traces` — /traces works
- `test_traces_reset_clears_all` — Reset works
- `test_scenario_switch_changes_responses` — Scenario switching works
**Fixtures:**
- `test_client` — `TestClient(create_app(mode="mock"))`
- `async_client` — For async endpoint tests if needed
**Pattern:** Use `from fastapi.testclient import TestClient`

### `src/agentlens/server/models.py`
**Purpose:** Request/response models for OpenAI compatibility
**Classes:**
- `ChatMessage(BaseModel)`
  - role: Literal["system", "user", "assistant", "tool"]
  - content: str | None = None
  - tool_calls: list[ToolCall] | None = None
  - tool_call_id: str | None = None
- `ToolCall(BaseModel)`
  - id: str
  - type: Literal["function"] = "function"
  - function: ToolFunction
- `ToolFunction(BaseModel)`
  - name: str
  - arguments: str
- `ChatCompletionRequest(BaseModel)`
  - model: str
  - messages: list[ChatMessage]
  - tools: list[dict[str, Any]] | None = None
  - temperature: float = 1.0
  - max_tokens: int | None = None
- `Usage(BaseModel)`
  - prompt_tokens: int
  - completion_tokens: int
  - total_tokens: int
- `Choice(BaseModel)`
  - index: int = 0
  - message: ChatMessage
  - finish_reason: Literal["stop", "tool_calls"] = "stop"
- `ChatCompletionResponse(BaseModel)`
  - id: str
  - object: Literal["chat.completion"] = "chat.completion"
  - created: int
  - model: str
  - choices: list[Choice]
  - usage: Usage

## Verification

After implementation:
1. `uv run pytest tests/test_server.py` — Server tests pass
2. `uv run uvicorn agentlens.server.proxy:create_app --factory --port 8650` — Server starts (CLI not yet available, use uvicorn directly)
3. `curl http://localhost:8650/health` — Returns ok
4. `curl -X POST http://localhost:8650/v1/chat/completions -H "Content-Type: application/json" -d '{"model":"test","messages":[{"role":"user","content":"hi"}]}'` — Returns canned response

**Note:** The `agentlens serve` CLI command is created in Phase 4. For Phase 2 verification, use uvicorn directly or rely on TestClient-based tests.
