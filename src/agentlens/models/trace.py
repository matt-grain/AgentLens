from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class SpanType(StrEnum):
    LLM_CALL = "llm_call"
    TOOL_CALL = "tool_call"
    DECISION = "decision"
    ERROR = "error"
    ESCALATION = "escalation"


class SpanStatus(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    TIMEOUT = "timeout"


class TokenUsage(BaseModel, frozen=True):
    input_tokens: int
    output_tokens: int


class Span(BaseModel, frozen=True):
    """Individual step in agent execution.

    Output key conventions (contract for evaluators):
    - LLM_CALL: output={"content": "response text", "tool_calls": [...]}
    - TOOL_CALL: output={"result": "tool output text"}
    - ERROR:     output={"error": "error message"}
    - ESCALATION: output={"reason": "why escalated"}
    - DECISION:  output={"decision": "what was decided"}
    """

    id: str
    span_type: SpanType
    name: str
    input: dict[str, Any]
    output: dict[str, Any] | None = None
    status: SpanStatus = SpanStatus.SUCCESS
    start_time: datetime
    end_time: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)
    parent_id: str | None = None
    token_usage: TokenUsage | None = None

    @property
    def duration_ms(self) -> int:
        return int((self.end_time - self.start_time).total_seconds() * 1000)


class Trace(BaseModel):
    """Complete agent execution record. Not frozen — spans are appended during capture."""

    id: str
    task: str
    agent_name: str
    spans: list[Span]
    final_output: str | None = None
    started_at: datetime
    completed_at: datetime

    @property
    def total_tokens(self) -> TokenUsage | None:
        usages = [s.token_usage for s in self.spans if s.token_usage is not None]
        if not usages:
            return None
        return TokenUsage(
            input_tokens=sum(u.input_tokens for u in usages),
            output_tokens=sum(u.output_tokens for u in usages),
        )

    @property
    def duration_ms(self) -> int:
        return int((self.completed_at - self.started_at).total_seconds() * 1000)
