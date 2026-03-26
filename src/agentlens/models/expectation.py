from __future__ import annotations

from pydantic import BaseModel, Field


class TaskExpectation(BaseModel, frozen=True):
    expected_output: str | None = None
    expected_tools: list[str] = Field(default_factory=list)
    forbidden_tools: list[str] = Field(default_factory=list)
    max_steps: int | None = None
    policies: list[str] = Field(default_factory=list)
    expected_escalation: bool = False
