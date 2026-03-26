"""Auto tool-call wrapping for mailbox responses."""

from __future__ import annotations

import json
import uuid
from typing import Any


def maybe_wrap_tool_calls(
    content: str,
    tool_calls: list[dict[str, Any]],
    request_tools: list[dict[str, Any]] | None,
) -> tuple[str, list[dict[str, Any]]]:
    """If content is JSON dict and request has tools, wrap as tool_calls.

    Returns (content, tool_calls) — possibly modified.
    This is what CrewAI/instructor expects for structured output via tool schemas.
    """
    if tool_calls or not request_tools or not content:
        return content, tool_calls

    try:
        parsed = json.loads(content)
    except (json.JSONDecodeError, ValueError):
        return content, tool_calls

    if not isinstance(parsed, dict):
        return content, tool_calls

    first_tool = request_tools[0]
    tool_name = first_tool.get("function", {}).get("name", "unknown")
    wrapped: list[dict[str, Any]] = [
        {
            "id": f"call_{uuid.uuid4().hex[:8]}",
            "type": "function",
            "function": {
                "name": tool_name,
                "arguments": json.dumps(parsed),
            },
        }
    ]
    return "", wrapped
