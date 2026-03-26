"""FastAPI app with OpenAI-compatible endpoints for trace capture."""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

import httpx
from fastapi import FastAPI, HTTPException

from agentlens.server.canned import REGISTRY, CannedResponse
from agentlens.server.collector import TraceCollector
from agentlens.server.mailbox import MailboxQueue, MailboxResponse
from agentlens.server.models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    Choice,
    Usage,
)
from agentlens.server.wrapping import maybe_wrap_tool_calls


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


def _build_openai_response(
    content: str,
    tool_calls: list[dict[str, Any]],
    usage: dict[str, int],
    model: str,
) -> ChatCompletionResponse:
    finish_reason: Literal["stop", "tool_calls"] = "tool_calls" if tool_calls else "stop"
    return ChatCompletionResponse(
        id=f"chatcmpl-{uuid.uuid4().hex[:8]}",
        created=int(datetime.now(UTC).timestamp()),
        model=model,
        choices=[
            Choice(
                message=ChatMessage(role="assistant", content=content or None),
                finish_reason=finish_reason,
            )
        ],
        usage=Usage(
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0),
        ),
    )


def create_app(
    mode: Literal["mock", "proxy", "mailbox"] = "mock",
    proxy_target: str | None = None,
    scenario: str = "happy_path",
    timeout: float = 300.0,
) -> FastAPI:
    app = FastAPI(title="AgentLens Proxy")

    collector = TraceCollector()
    active_scenario: list[str] = [scenario]
    mailbox: MailboxQueue | None = MailboxQueue(timeout=timeout) if mode == "mailbox" else None

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
        elif mode == "mailbox":
            assert mailbox is not None
            entry = mailbox.enqueue(
                [m.model_dump() for m in request.messages],
                request.model,
                request.tools if request.tools is not None else [],
            )
            try:
                mb_response = await mailbox.wait_for_response(entry.request_id)
            except TimeoutError as exc:
                raise HTTPException(status_code=408, detail="Mailbox request timed out") from exc
            content = mb_response.content
            tool_calls_raw = mb_response.tool_calls
            content, tool_calls_raw = maybe_wrap_tool_calls(content, tool_calls_raw, request.tools)
            usage: dict[str, Any] = {"prompt_tokens": 0, "completion_tokens": 0}
            response = _build_openai_response(content, tool_calls_raw, usage, request.model)
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

    if mode == "mailbox":
        assert mailbox is not None
        _register_mailbox_endpoints(app, mailbox)

    return app


def _register_mailbox_endpoints(app: FastAPI, mailbox: MailboxQueue) -> None:
    """Register the four /mailbox endpoints onto the app."""

    @app.get("/mailbox/stats")
    async def mailbox_stats() -> dict[str, Any]:  # type: ignore[reportUnusedFunction]
        return mailbox.stats()

    @app.get("/mailbox")
    async def list_mailbox() -> list[dict[str, Any]]:  # type: ignore[reportUnusedFunction]
        now = time.time()
        result: list[dict[str, Any]] = []
        for entry in mailbox.list_pending():
            last_user = next(
                (m["content"] for m in reversed(entry.messages) if m.get("role") == "user"),
                "",
            )
            result.append(
                {
                    "request_id": entry.request_id,
                    "model": entry.model,
                    "preview": (last_user or "")[:100],
                    "age_seconds": round(now - entry.timestamp, 2),
                }
            )
        return result

    @app.get("/mailbox/{request_id}")
    async def get_mailbox_entry(request_id: int) -> dict[str, Any]:  # type: ignore[reportUnusedFunction]
        entry = mailbox.get_entry(request_id)
        if entry is None:
            raise HTTPException(status_code=404, detail=f"Request {request_id} not found")
        tools_info = [
            {
                "name": t.get("function", {}).get("name", "unknown"),
                "parameters": t.get("function", {}).get("parameters", {}),
            }
            for t in entry.tools
        ]
        response_hint: dict[str, Any] = {
            "format": "plain text or JSON with tool_calls",
            "example_text": {"response": "Your answer here"},
            "example_tool_call": {
                "content": "",
                "tool_calls": [
                    {"id": "call_001", "type": "function", "function": {"name": "search", "arguments": "{}"}}
                ],
            },
        }
        if tools_info:
            response_hint["available_tools"] = tools_info
            response_hint["auto_wrap_note"] = (
                "If you send plain JSON matching a tool schema, it will be auto-wrapped as a tool_call response."
            )
        return {
            "request_id": entry.request_id,
            "model": entry.model,
            "messages": entry.messages,
            "tools": entry.tools,
            "response_hint": response_hint,
            "age_seconds": round(time.time() - entry.timestamp, 2),
        }

    @app.post("/mailbox/{request_id}")
    async def submit_mailbox_response(request_id: int, body: dict[str, Any]) -> dict[str, str]:  # type: ignore[reportUnusedFunction]
        if "response" in body:
            mb_response = MailboxResponse(content=body["response"])
        else:
            mb_response = MailboxResponse(
                content=body.get("content", ""),
                tool_calls=body.get("tool_calls", []),
            )
        try:
            mailbox.submit_response(request_id, mb_response)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=f"Request {request_id} not found") from exc
        return {"status": "submitted"}


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
