"""Async mailbox queue for human/AI-in-the-loop evaluation."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from pydantic import BaseModel, Field


def _empty_dict_list() -> list[dict[str, Any]]:
    return []


class MailboxEntry(BaseModel):
    request_id: int
    messages: list[dict[str, Any]]
    model: str
    tools: list[dict[str, Any]] = Field(default_factory=_empty_dict_list)
    timestamp: float = Field(default_factory=time.time)


class MailboxResponse(BaseModel):
    content: str = ""
    tool_calls: list[dict[str, Any]] = Field(default_factory=_empty_dict_list)


class MailboxQueue:
    """Thread-safe async queue for mailbox-mode request/response pairing."""

    def __init__(self, timeout: float = 300.0) -> None:
        self._pending: dict[int, MailboxEntry] = {}
        self._events: dict[int, asyncio.Event] = {}
        self._responses: dict[int, MailboxResponse] = {}
        self._counter: int = 0
        self._timeout: float = timeout
        self._served: int = 0

    def enqueue(
        self,
        messages: list[dict[str, Any]],
        model: str,
        tools: list[dict[str, Any]],
    ) -> MailboxEntry:
        self._counter += 1
        entry = MailboxEntry(request_id=self._counter, messages=messages, model=model, tools=tools)
        self._pending[self._counter] = entry
        self._events[self._counter] = asyncio.Event()
        return entry

    async def wait_for_response(self, request_id: int) -> MailboxResponse:
        event = self._events[request_id]
        try:
            await asyncio.wait_for(event.wait(), timeout=self._timeout)
        except TimeoutError as exc:
            self._pending.pop(request_id, None)
            self._events.pop(request_id, None)
            raise TimeoutError(f"Request {request_id} timed out after {self._timeout}s") from exc
        self._pending.pop(request_id, None)
        self._events.pop(request_id, None)
        self._served += 1
        return self._responses.pop(request_id)

    def submit_response(self, request_id: int, response: MailboxResponse) -> None:
        if request_id not in self._pending:
            raise ValueError(f"Unknown request ID: {request_id}")
        self._responses[request_id] = response
        self._events[request_id].set()

    def list_pending(self) -> list[MailboxEntry]:
        return sorted(self._pending.values(), key=lambda e: e.request_id)

    def get_entry(self, request_id: int) -> MailboxEntry | None:
        return self._pending.get(request_id)

    def stats(self) -> dict[str, Any]:
        return {"pending": len(self._pending), "served": self._served, "timeout": self._timeout}
