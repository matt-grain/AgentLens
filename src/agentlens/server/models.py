"""Request/response models for OpenAI API compatibility."""

from __future__ import annotations

from enum import StrEnum, unique
from typing import Any, Literal

from pydantic import BaseModel


@unique
class ServerMode(StrEnum):
    MOCK = "mock"
    PROXY = "proxy"
    MAILBOX = "mailbox"


@unique
class FinishReason(StrEnum):
    STOP = "stop"
    TOOL_CALLS = "tool_calls"


@unique
class MessageRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ToolFunction(BaseModel):
    name: str
    arguments: str


class ToolCall(BaseModel):
    id: str
    type: Literal["function"] = "function"
    function: ToolFunction


class ChatMessage(BaseModel):
    role: MessageRole
    content: str | None = None
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    tools: list[dict[str, Any]] | None = None  # pass-through to upstream, shape varies
    temperature: float = 1.0
    max_tokens: int | None = None


class Usage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class Choice(BaseModel):
    index: int = 0
    message: ChatMessage
    finish_reason: FinishReason = FinishReason.STOP


class ChatCompletionResponse(BaseModel):
    id: str
    object: Literal["chat.completion"] = "chat.completion"
    created: int
    model: str
    choices: list[Choice]
    usage: Usage
