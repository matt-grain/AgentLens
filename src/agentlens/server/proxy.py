"""FastAPI app with OpenAI-compatible endpoints for trace capture."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

import httpx
from fastapi import FastAPI, HTTPException

from agentlens.server.canned import REGISTRY, CannedResponse
from agentlens.server.collector import TraceCollector
from agentlens.server.models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    Choice,
    Usage,
)


def _canned_to_response(canned: CannedResponse, model: str) -> ChatCompletionResponse:
    finish_reason: Literal["stop", "tool_calls"] = "tool_calls" if canned.tool_calls else "stop"
    return ChatCompletionResponse(
        id=f"chatcmpl-{uuid.uuid4().hex[:8]}",
        created=int(datetime.now(UTC).timestamp()),
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


def create_app(
    mode: Literal["mock", "proxy"] = "mock",
    proxy_target: str | None = None,
    scenario: str = "happy_path",
) -> FastAPI:
    app = FastAPI(title="AgentLens Proxy")

    collector = TraceCollector()
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
        if mode == "mock":
            canned = REGISTRY.next_response(active_scenario[0])
            response = _canned_to_response(canned, request.model)
            tool_calls_raw = canned.tool_calls
            content = canned.content
            usage = canned.usage
        else:
            response, content, tool_calls_raw, usage = await _proxy_request(request, proxy_target)

        collector.record_llm_call(request.messages, content, tool_calls_raw, usage)

        resp_dict = response.model_dump()
        if tool_calls_raw:
            resp_dict["choices"][0]["message"]["tool_calls"] = tool_calls_raw
        return resp_dict

    @app.get("/traces")
    async def list_traces() -> list[dict[str, Any]]:  # type: ignore[reportUnusedFunction]
        return [t.model_dump(mode="json") for t in collector.traces]

    @app.get("/traces/{trace_id}")
    async def get_trace(trace_id: str) -> dict[str, Any]:  # type: ignore[reportUnusedFunction]
        match = collector.get_trace(trace_id)
        if match is None:
            raise HTTPException(status_code=404, detail=f"Trace {trace_id!r} not found")
        return match.model_dump(mode="json")

    @app.post("/traces/reset")
    async def reset_traces() -> dict[str, str]:  # type: ignore[reportUnusedFunction]
        collector.reset()
        return {"status": "reset"}

    @app.post("/scenario/{name}")
    async def switch_scenario(name: str) -> dict[str, str]:  # type: ignore[reportUnusedFunction]
        if mode != "mock":
            raise HTTPException(status_code=400, detail="Scenario switching only available in mock mode")
        collector.reset()
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
