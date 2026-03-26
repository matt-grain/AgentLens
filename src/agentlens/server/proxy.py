"""FastAPI app with OpenAI-compatible endpoints for trace capture."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

import httpx
from fastapi import FastAPI, HTTPException

from agentlens.models.trace import Span, SpanStatus, SpanType, TokenUsage, Trace
from agentlens.server.canned import REGISTRY, CannedResponse
from agentlens.server.models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    Choice,
    Usage,
)


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _now() -> datetime:
    return datetime.now(UTC)


def _build_llm_span(
    messages: list[ChatMessage],
    content: str,
    tool_calls: list[dict[str, Any]],
    usage: dict[str, int],
    llm_span_id: str,
) -> Span:
    last_user = next((m.content for m in reversed(messages) if m.role == "user"), "")
    token_usage = TokenUsage(
        input_tokens=usage.get("prompt_tokens", 0),
        output_tokens=usage.get("completion_tokens", 0),
    )
    now = _now()
    return Span(
        id=llm_span_id,
        span_type=SpanType.LLM_CALL,
        name="llm_call",
        input={"messages": [last_user]},
        output={"content": content, "tool_calls": tool_calls},
        status=SpanStatus.SUCCESS,
        start_time=now,
        end_time=now,
        token_usage=token_usage,
    )


def _build_tool_spans(tool_calls: list[dict[str, Any]], parent_id: str) -> list[Span]:
    spans: list[Span] = []
    for tc in tool_calls:
        fn = tc.get("function", {})
        now = _now()
        spans.append(
            Span(
                id=_new_id(),
                span_type=SpanType.TOOL_CALL,
                name=fn.get("name", "unknown"),
                input={"arguments": fn.get("arguments", "")},
                output={"result": ""},
                status=SpanStatus.SUCCESS,
                start_time=now,
                end_time=now,
                parent_id=parent_id,
            )
        )
    return spans


def _canned_to_response(canned: CannedResponse, model: str) -> ChatCompletionResponse:
    finish_reason: Literal["stop", "tool_calls"] = "tool_calls" if canned.tool_calls else "stop"
    return ChatCompletionResponse(
        id=f"chatcmpl-{uuid.uuid4().hex[:8]}",
        created=int(_now().timestamp()),
        model=model,
        choices=[
            Choice(
                message=ChatMessage(
                    role="assistant",
                    content=canned.content or None,
                    tool_calls=None,  # raw dicts returned in .model_dump() below
                ),
                finish_reason=finish_reason,
            )
        ],
        usage=Usage(
            prompt_tokens=canned.usage.get("prompt_tokens", 100),
            completion_tokens=canned.usage.get("completion_tokens", 50),
            total_tokens=canned.usage.get("prompt_tokens", 100) + canned.usage.get("completion_tokens", 50),
        ),
    )


def _finalize_trace(
    spans: list[Span],
    task: str,
    traces: list[Trace],
) -> None:
    if not spans:
        return
    now = _now()
    last_llm = next(
        (s for s in reversed(spans) if s.span_type == SpanType.LLM_CALL),
        None,
    )
    final_output = str(last_llm.output.get("content", "")) if last_llm and last_llm.output else None
    traces.append(
        Trace(
            id=_new_id(),
            task=task,
            agent_name="agentlens-proxy",
            spans=list(spans),
            final_output=final_output,
            started_at=spans[0].start_time,
            completed_at=now,
        )
    )


def create_app(
    mode: Literal["mock", "proxy"] = "mock",
    proxy_target: str | None = None,
    scenario: str = "happy_path",
) -> FastAPI:
    app = FastAPI(title="AgentLens Proxy")

    traces: list[Trace] = []
    current_spans: list[Span] = []
    current_task: list[str] = ["unknown"]  # mutable container for closure capture
    active_scenario: list[str] = [scenario]

    @app.get("/health")
    async def health() -> dict[str, str]:  # type: ignore[reportUnusedFunction]
        return {"status": "ok", "mode": mode}

    @app.get("/v1/models")
    async def list_models() -> dict[str, Any]:  # type: ignore[reportUnusedFunction]
        return {
            "object": "list",
            "data": [{"id": "agentlens-mock", "object": "model", "created": 0, "owned_by": "agentlens"}],
        }

    @app.post("/v1/chat/completions")
    async def chat_completions(request: ChatCompletionRequest) -> dict[str, Any]:  # type: ignore[reportUnusedFunction]
        first_user = next((m.content for m in request.messages if m.role == "user"), "unknown")
        if not current_spans:
            current_task[0] = first_user or "unknown"

        if mode == "mock":
            canned = REGISTRY.next_response(active_scenario[0])
            response = _canned_to_response(canned, request.model)
            tool_calls_raw = canned.tool_calls
            content = canned.content
            usage = canned.usage
        else:
            response, content, tool_calls_raw, usage = await _proxy_request(request, proxy_target)

        llm_id = _new_id()
        current_spans.append(_build_llm_span(request.messages, content, tool_calls_raw, usage, llm_id))
        current_spans.extend(_build_tool_spans(tool_calls_raw, llm_id))

        resp_dict = response.model_dump()
        if tool_calls_raw:
            resp_dict["choices"][0]["message"]["tool_calls"] = tool_calls_raw
        return resp_dict

    @app.get("/traces")
    async def list_traces() -> list[dict[str, Any]]:  # type: ignore[reportUnusedFunction]
        return [t.model_dump(mode="json") for t in traces]

    @app.get("/traces/{trace_id}")
    async def get_trace(trace_id: str) -> dict[str, Any]:  # type: ignore[reportUnusedFunction]
        match = next((t for t in traces if t.id == trace_id), None)
        if match is None:
            raise HTTPException(status_code=404, detail=f"Trace {trace_id!r} not found")
        return match.model_dump(mode="json")

    @app.post("/traces/reset")
    async def reset_traces() -> dict[str, str]:  # type: ignore[reportUnusedFunction]
        _finalize_trace(current_spans, current_task[0], traces)
        current_spans.clear()
        current_task[0] = "unknown"
        return {"status": "reset"}

    @app.post("/scenario/{name}")
    async def switch_scenario(name: str) -> dict[str, str]:  # type: ignore[reportUnusedFunction]
        if mode != "mock":
            raise HTTPException(status_code=400, detail="Scenario switching only available in mock mode")
        _finalize_trace(current_spans, current_task[0], traces)
        current_spans.clear()
        current_task[0] = "unknown"
        active_scenario[0] = name
        REGISTRY.reset(name)
        return {"status": "switched", "scenario": name}

    return app


async def _proxy_request(
    request: ChatCompletionRequest,
    proxy_target: str | None,
) -> tuple[ChatCompletionResponse, str, list[dict[str, Any]], dict[str, int]]:
    if proxy_target is None:
        raise HTTPException(status_code=500, detail="proxy_target must be set in proxy mode")
    async with httpx.AsyncClient() as client:
        upstream = await client.post(
            f"{proxy_target}/v1/chat/completions",
            json=request.model_dump(exclude_none=True),
            timeout=60.0,
        )
        upstream.raise_for_status()
    data: dict[str, Any] = upstream.json()
    choice = data["choices"][0]
    msg = choice["message"]
    content: str = msg.get("content") or ""
    tool_calls_raw: list[dict[str, Any]] = msg.get("tool_calls") or []
    raw_usage: dict[str, Any] = data.get("usage", {})
    usage: dict[str, int] = {
        "prompt_tokens": int(raw_usage.get("prompt_tokens", 0)),
        "completion_tokens": int(raw_usage.get("completion_tokens", 0)),
    }
    finish_reason: Literal["stop", "tool_calls"] = "tool_calls" if tool_calls_raw else "stop"
    response = ChatCompletionResponse(
        id=data.get("id", f"chatcmpl-{uuid.uuid4().hex[:8]}"),
        created=data.get("created", int(datetime.now(UTC).timestamp())),
        model=data.get("model", request.model),
        choices=[
            Choice(
                message=ChatMessage(role="assistant", content=content or None),
                finish_reason=finish_reason,
            )
        ],
        usage=Usage(
            prompt_tokens=usage["prompt_tokens"],
            completion_tokens=usage["completion_tokens"],
            total_tokens=usage["prompt_tokens"] + usage["completion_tokens"],
        ),
    )
    return response, content, tool_calls_raw, usage
