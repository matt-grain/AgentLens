"""Tests for server request/response Pydantic models."""

from __future__ import annotations

from agentlens.server.models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    Choice,
    FinishReason,
    MessageRole,
    Usage,
)


class TestChatMessage:
    def test_chat_message_user_role(self) -> None:
        # Arrange & Act
        msg = ChatMessage(role=MessageRole.USER, content="Hello")

        # Assert
        assert msg.role == MessageRole.USER
        assert msg.content == "Hello"
        assert msg.tool_calls is None
        assert msg.tool_call_id is None

    def test_chat_message_role_string_coercion(self) -> None:
        # Arrange & Act — Pydantic should coerce the string to MessageRole
        msg = ChatMessage(role="assistant", content="Hi")  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]  # intentional: testing Pydantic string coercion

        # Assert
        assert msg.role == MessageRole.ASSISTANT


class TestChatCompletionRequest:
    def test_chat_completion_request_defaults(self) -> None:
        # Arrange & Act
        req = ChatCompletionRequest(
            model="gpt-4",
            messages=[ChatMessage(role=MessageRole.USER, content="test")],
        )

        # Assert
        assert req.model == "gpt-4"
        assert len(req.messages) == 1
        assert req.temperature == 1.0
        assert req.max_tokens is None
        assert req.tools is None


class TestChatCompletionResponse:
    def test_chat_completion_response_structure(self) -> None:
        # Arrange & Act
        response = ChatCompletionResponse(
            id="chatcmpl-abc123",
            created=1700000000,
            model="gpt-4",
            choices=[
                Choice(
                    message=ChatMessage(role=MessageRole.ASSISTANT, content="Hello"),
                    finish_reason=FinishReason.STOP,
                )
            ],
            usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        )

        # Assert
        assert response.id == "chatcmpl-abc123"
        assert response.object == "chat.completion"
        assert response.choices[0].finish_reason == FinishReason.STOP
        assert response.choices[0].message.role == MessageRole.ASSISTANT
        assert response.usage.total_tokens == 15

    def test_choice_default_finish_reason_is_stop(self) -> None:
        # Arrange & Act
        choice = Choice(message=ChatMessage(role=MessageRole.ASSISTANT, content="done"))

        # Assert
        assert choice.finish_reason == FinishReason.STOP
        assert choice.index == 0
