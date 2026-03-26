"""Canned responses for mock mode demo scenarios."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CannedResponse(BaseModel, frozen=True):
    content: str
    # Plain dicts — serialize directly into OpenAI-compatible JSON without extra conversion.
    tool_calls: list[dict[str, Any]] = Field(default_factory=lambda: [])
    usage: dict[str, int] = Field(default_factory=lambda: {"prompt_tokens": 100, "completion_tokens": 50})


class CannedRegistry:
    """Singleton registry for ordered per-scenario canned responses."""

    def __init__(self) -> None:
        self.responses: dict[str, list[CannedResponse]] = {}
        self._index: dict[str, int] = {}

    def register(self, scenario: str, responses: list[CannedResponse]) -> None:
        self.responses[scenario] = responses
        self._index[scenario] = 0

    def next_response(self, scenario: str) -> CannedResponse:
        items = self.responses[scenario]
        idx = self._index.get(scenario, 0)
        response = items[idx % len(items)]
        self._index[scenario] = (idx + 1) % len(items)
        return response

    def reset(self, scenario: str | None = None) -> None:
        if scenario is None:
            self._index = {k: 0 for k in self._index}
        else:
            self._index[scenario] = 0


def _make_tool_call(call_id: str, name: str, arguments: str) -> dict[str, Any]:
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": arguments}}


REGISTRY = CannedRegistry()

REGISTRY.register(
    "happy_path",
    [
        CannedResponse(content="I'll search for France and Germany GDP data and compare them."),
        CannedResponse(
            content="",
            tool_calls=[_make_tool_call("call_001", "search", '{"query":"France GDP 2023"}')],
        ),
        CannedResponse(
            content="",
            tool_calls=[_make_tool_call("call_002", "search", '{"query":"Germany GDP 2023"}')],
        ),
        CannedResponse(
            content="France's GDP in 2023 was $3.05 trillion, while Germany's was $4.43 trillion"
            " — a difference of $1.38 trillion.",
        ),
    ],
)

REGISTRY.register(
    "loop",
    [
        CannedResponse(content="I'll search for the GDP data."),
        CannedResponse(
            content="",
            tool_calls=[_make_tool_call("call_001", "search", '{"query":"France GDP 2023"}')],
        ),
        CannedResponse(
            content="",
            tool_calls=[_make_tool_call("call_002", "search", '{"query":"France GDP 2023"}')],
        ),
        CannedResponse(
            content="",
            tool_calls=[_make_tool_call("call_003", "search", '{"query":"France GDP 2023"}')],
        ),
        CannedResponse(
            content="Based on my research, France's GDP in 2023 was approximately $3.05 trillion.",
        ),
    ],
)

REGISTRY.register(
    "risk",
    [
        CannedResponse(
            content="I'll search and send an email report.",
            tool_calls=[_make_tool_call("call_001", "send_email", '{"to":"boss@example.com","subject":"GDP Report"}')],
        ),
        CannedResponse(
            content="",
            tool_calls=[_make_tool_call("call_002", "search", '{"query":"France GDP 2023"}')],
        ),
        CannedResponse(
            content="France's GDP grew by 47% in 2023, reaching $3.05 trillion.",
        ),
    ],
)
