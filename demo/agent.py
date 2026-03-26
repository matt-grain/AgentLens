"""Research assistant agent for live demos."""

from __future__ import annotations

import json
from typing import Any

import httpx

_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search",
            "description": "Search for information on the web.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "Evaluate a simple arithmetic expression.",
            "parameters": {
                "type": "object",
                "properties": {"expression": {"type": "string"}},
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cite_source",
            "description": "Record a source citation.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_email",
            "description": "Send an email message.",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {"type": "string"},
                    "subject": {"type": "string"},
                },
                "required": ["to", "subject"],
            },
        },
    },
]

_CANNED_SEARCH: dict[str, str] = {
    "france gdp 2023": "France GDP 2023: $3.05 trillion (World Bank)",
    "germany gdp 2023": "Germany GDP 2023: $4.43 trillion (World Bank)",
}

_MAX_ITERATIONS = 10


class ResearchAgent:
    """Synchronous research assistant that calls the AgentLens proxy."""

    def __init__(self, base_url: str = "http://localhost:8650") -> None:
        self._client = httpx.Client(base_url=base_url, timeout=30.0)
        self.tools = _TOOL_DEFINITIONS

    def run(self, task: str) -> str:
        """Execute a research task, returning the final answer."""
        messages: list[dict[str, Any]] = [{"role": "user", "content": task}]

        for _ in range(_MAX_ITERATIONS):
            response = self._call_llm(messages)
            content: str = response.get("content") or ""
            tool_calls: list[dict[str, Any]] = response.get("tool_calls") or []

            messages.append({"role": "assistant", "content": content, "tool_calls": tool_calls})

            if not tool_calls:
                return content

            for tc in tool_calls:
                result = self._execute_tool(tc["function"]["name"], tc["function"].get("arguments", "{}"))
                messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result})

        return "Max iterations reached without final answer."

    def _call_llm(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        """POST to /v1/chat/completions and return the message dict."""
        payload: dict[str, Any] = {
            "model": "agentlens-mock",
            "messages": messages,
            "tools": self.tools,
        }
        resp = self._client.post("/v1/chat/completions", json=payload)
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        return dict(data["choices"][0]["message"])  # type: ignore[return-value]

    def _execute_tool(self, name: str, args_json: str) -> str:
        """Simulate tool execution and return a string result."""
        args: dict[str, Any] = json.loads(args_json) if args_json else {}
        dispatch = {
            "search": self._tool_search,
            "calculator": self._tool_calculator,
            "cite_source": self._tool_cite_source,
            "send_email": self._tool_send_email,
        }
        handler = dispatch.get(name)
        if handler is None:
            return f"Unknown tool: {name}"
        return handler(args)

    def _tool_search(self, args: dict[str, Any]) -> str:
        query: str = str(args.get("query", "")).lower()
        for key, result in _CANNED_SEARCH.items():
            if key in query:
                return result
        return f"No results found for: {args.get('query', '')}"

    def _tool_calculator(self, args: dict[str, Any]) -> str:
        expression: str = str(args.get("expression", "0"))
        try:
            result = eval(expression, {"__builtins__": {}})  # noqa: S307
            return str(result)
        except Exception:
            return "Error: invalid expression"

    def _tool_cite_source(self, args: dict[str, Any]) -> str:
        return f"cited: {args.get('url', '')}"

    def _tool_send_email(self, args: dict[str, Any]) -> str:
        return f"sent to {args.get('to', 'unknown')}"
