"""Unit tests for auto tool-call wrapping logic."""

from __future__ import annotations

import json

from agentlens.server.wrapping import maybe_wrap_tool_calls


def test_json_content_with_tools_gets_wrapped() -> None:
    # Arrange
    content = '{"proposal": "test", "reasoning": "test"}'
    tools = [{"function": {"name": "HypothesisOutput", "parameters": {}}}]

    # Act
    new_content, new_tool_calls = maybe_wrap_tool_calls(content, [], tools)

    # Assert
    assert new_content == ""
    assert len(new_tool_calls) == 1
    assert new_tool_calls[0]["function"]["name"] == "HypothesisOutput"
    assert new_tool_calls[0]["type"] == "function"
    assert json.loads(new_tool_calls[0]["function"]["arguments"]) == {"proposal": "test", "reasoning": "test"}


def test_plain_text_with_tools_not_wrapped() -> None:
    # Arrange
    content = "This is a plain text response"
    tools = [{"function": {"name": "search", "parameters": {}}}]

    # Act
    new_content, new_tool_calls = maybe_wrap_tool_calls(content, [], tools)

    # Assert
    assert new_content == "This is a plain text response"
    assert new_tool_calls == []


def test_no_tools_not_wrapped() -> None:
    # Arrange
    content = '{"key": "value"}'

    # Act
    new_content, new_tool_calls = maybe_wrap_tool_calls(content, [], None)

    # Assert
    assert new_content == '{"key": "value"}'
    assert new_tool_calls == []


def test_empty_tools_list_not_wrapped() -> None:
    # Arrange
    content = '{"key": "value"}'

    # Act
    new_content, new_tool_calls = maybe_wrap_tool_calls(content, [], [])

    # Assert
    assert new_content == '{"key": "value"}'
    assert new_tool_calls == []


def test_existing_tool_calls_not_modified() -> None:
    # Arrange
    existing: list[dict] = [{"id": "call_1", "type": "function", "function": {"name": "x", "arguments": "{}"}}]
    content = '{"key": "value"}'
    tools = [{"function": {"name": "search"}}]

    # Act
    new_content, new_tool_calls = maybe_wrap_tool_calls(content, existing, tools)

    # Assert
    assert new_content == '{"key": "value"}'
    assert new_tool_calls == existing


def test_json_list_not_wrapped() -> None:
    # Arrange
    content = "[1, 2, 3]"
    tools = [{"function": {"name": "search"}}]

    # Act
    new_content, new_tool_calls = maybe_wrap_tool_calls(content, [], tools)

    # Assert
    assert new_content == "[1, 2, 3]"
    assert new_tool_calls == []


def test_empty_content_not_wrapped() -> None:
    # Arrange
    tools = [{"function": {"name": "search"}}]

    # Act
    new_content, new_tool_calls = maybe_wrap_tool_calls("", [], tools)

    # Assert
    assert new_content == ""
    assert new_tool_calls == []


def test_wrapped_tool_call_id_has_expected_format() -> None:
    # Arrange
    content = '{"answer": 42}'
    tools = [{"function": {"name": "AnswerTool", "parameters": {}}}]

    # Act
    _, new_tool_calls = maybe_wrap_tool_calls(content, [], tools)

    # Assert
    call_id: str = new_tool_calls[0]["id"]
    assert call_id.startswith("call_")
    assert len(call_id) == len("call_") + 8


def test_uses_first_tool_name_when_multiple_tools_present() -> None:
    # Arrange
    content = '{"result": "ok"}'
    tools = [
        {"function": {"name": "PrimaryTool"}},
        {"function": {"name": "SecondaryTool"}},
    ]

    # Act
    _, new_tool_calls = maybe_wrap_tool_calls(content, [], tools)

    # Assert
    assert new_tool_calls[0]["function"]["name"] == "PrimaryTool"
