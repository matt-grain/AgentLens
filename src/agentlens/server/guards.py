"""Real-time evaluation guards — circuit breaker for agent responses."""

from __future__ import annotations

import logging
from datetime import datetime
from enum import StrEnum, unique
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from agentlens.evaluators import Evaluator
from agentlens.models.evaluation import EvalResult
from agentlens.models.expectation import TaskExpectation
from agentlens.server.collector import TraceCollector
from agentlens.server.mailbox import MailboxQueue
from agentlens.server.models import ChatMessage

logger = logging.getLogger(__name__)


@unique
class GuardAction(StrEnum):
    WARN = "warn"
    BLOCK = "block"
    ESCALATE = "escalate"


class GuardRule(BaseModel, frozen=True):
    """A single guard rule: trigger when evaluator score < threshold."""

    evaluator_name: str
    threshold: float = 0.5
    action: GuardAction = GuardAction.WARN
    message: str | None = None


class GuardConfig(BaseModel, frozen=True):
    """Configuration for real-time evaluation guards."""

    rules: list[GuardRule] = Field(default_factory=lambda: list[GuardRule]())
    enabled: bool = True

    @classmethod
    def from_yaml(cls, path: Path) -> GuardConfig:
        data = yaml.safe_load(path.read_text())
        return cls.model_validate(data)


class GuardResult(BaseModel, frozen=True):
    """Outcome of a guard check."""

    triggered: bool
    rule: GuardRule | None = None
    eval_result: EvalResult | None = None
    action_taken: GuardAction | None = None


def guard_check(
    collector: TraceCollector,
    content: str,
    tool_calls: list[dict[str, Any]],
    messages: list[ChatMessage],
    usage: dict[str, Any],
    config: GuardConfig,
    evaluators: list[Evaluator],
    start_time: datetime,
    expected: TaskExpectation | None = None,
) -> tuple[str, list[dict[str, Any]], GuardResult]:
    """Evaluate response against guard rules before returning to agent.

    Returns (possibly modified) content, tool_calls, and a GuardResult.
    """
    not_triggered = GuardResult(triggered=False)

    if not config.enabled or not config.rules:
        return content, tool_calls, not_triggered

    temp_trace = collector.build_temp_trace(messages, content, tool_calls, usage, start_time)

    rule_names = {r.evaluator_name for r in config.rules}
    relevant_evals = [e for e in evaluators if e.name in rule_names]

    results: list[EvalResult] = []
    for ev in relevant_evals:
        results.extend(ev.evaluate(temp_trace, expected))

    for rule in config.rules:
        matching = [r for r in results if r.evaluator_name == rule.evaluator_name and r.score < rule.threshold]
        if not matching:
            continue

        evidence = matching[0].message
        logger.warning(
            "Guard triggered: %s (score=%.2f, action=%s)", rule.evaluator_name, matching[0].score, rule.action
        )

        result = GuardResult(triggered=True, rule=rule, eval_result=matching[0], action_taken=rule.action)

        if rule.action == GuardAction.WARN:
            warning = rule.message or f"[GUARD WARNING: {evidence}]"
            return f"{content}\n\n{warning}", tool_calls, result

        if rule.action == GuardAction.BLOCK:
            rejection = rule.message or f"I need to reconsider this approach. {evidence} Please revise."
            return rejection, [], result

        if rule.action == GuardAction.ESCALATE:
            rejection = rule.message or f"Response held for review: {evidence}"
            return rejection, [], result

    return content, tool_calls, not_triggered


async def guard_check_async(
    collector: TraceCollector,
    content: str,
    tool_calls: list[dict[str, Any]],
    messages: list[ChatMessage],
    usage: dict[str, Any],
    config: GuardConfig,
    evaluators: list[Evaluator],
    mailbox: MailboxQueue | None,
    start_time: datetime,
    expected: TaskExpectation | None = None,
) -> tuple[str, list[dict[str, Any]], GuardResult]:
    """Async version of guard_check with mailbox escalation support."""
    not_triggered = GuardResult(triggered=False)

    if not config.enabled or not config.rules:
        return content, tool_calls, not_triggered

    temp_trace = collector.build_temp_trace(messages, content, tool_calls, usage, start_time)

    rule_names = {r.evaluator_name for r in config.rules}
    relevant_evals = [e for e in evaluators if e.name in rule_names]

    results: list[EvalResult] = []
    for ev in relevant_evals:
        results.extend(ev.evaluate(temp_trace, expected))

    for rule in config.rules:
        matching = [r for r in results if r.evaluator_name == rule.evaluator_name and r.score < rule.threshold]
        if not matching:
            continue

        evidence = matching[0].message
        logger.warning(
            "Guard triggered: %s (score=%.2f, action=%s)", rule.evaluator_name, matching[0].score, rule.action
        )

        result = GuardResult(triggered=True, rule=rule, eval_result=matching[0], action_taken=rule.action)

        if rule.action == GuardAction.WARN:
            warning = rule.message or f"[GUARD WARNING: {evidence}]"
            return f"{content}\n\n{warning}", tool_calls, result

        if rule.action == GuardAction.BLOCK:
            rejection = rule.message or f"I need to reconsider this approach. {evidence} Please revise."
            return rejection, [], result

        if rule.action == GuardAction.ESCALATE:
            if mailbox is not None:
                entry = mailbox.enqueue(
                    [{"role": "system", "content": f"GUARD ESCALATION: {evidence}"}]
                    + [m.model_dump() for m in messages],
                    "guard-escalation",
                    [],
                )
                mb_response = await mailbox.wait_for_response(entry.request_id)
                return mb_response.content, mb_response.tool_calls, result
            # Fallback to block if no mailbox
            rejection = rule.message or f"Response blocked by guard: {evidence}"
            return rejection, [], result

    return content, tool_calls, not_triggered
