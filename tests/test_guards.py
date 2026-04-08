"""Unit tests for real-time evaluation guards."""

from __future__ import annotations

from datetime import UTC, datetime

from agentlens.evaluators.behavior import LoopDetector
from agentlens.evaluators.risk import HallucinationFlagEvaluator, PolicyViolationEvaluator
from agentlens.models.expectation import TaskExpectation
from agentlens.server.collector import TraceCollector
from agentlens.server.guards import GuardAction, GuardConfig, GuardRule, guard_check
from agentlens.server.models import ChatMessage, MessageRole


def _make_messages(content: str = "test task") -> list[ChatMessage]:
    return [ChatMessage(role=MessageRole.USER, content=content)]


def _make_usage() -> dict[str, int]:
    return {"prompt_tokens": 10, "completion_tokens": 20}


# ---------------------------------------------------------------------------
# Pass-through tests
# ---------------------------------------------------------------------------


def test_guard_disabled_passes_through() -> None:
    config = GuardConfig(
        enabled=False, rules=[GuardRule(evaluator_name="hallucination_flag", action=GuardAction.BLOCK)]
    )
    collector = TraceCollector()
    content, tool_calls, result = guard_check(
        collector,
        "Some response with $500 claim",
        [],
        _make_messages(),
        _make_usage(),
        config,
        [HallucinationFlagEvaluator()],
        datetime.now(UTC),
    )
    assert content == "Some response with $500 claim"
    assert not result.triggered


def test_guard_no_rules_passes_through() -> None:
    config = GuardConfig(enabled=True, rules=[])
    collector = TraceCollector()
    content, tool_calls, result = guard_check(
        collector,
        "clean response",
        [],
        _make_messages(),
        _make_usage(),
        config,
        [HallucinationFlagEvaluator()],
        datetime.now(UTC),
    )
    assert content == "clean response"
    assert not result.triggered


def test_guard_score_above_threshold_passes_through() -> None:
    config = GuardConfig(
        rules=[GuardRule(evaluator_name="hallucination_flag", threshold=0.5, action=GuardAction.BLOCK)]
    )
    collector = TraceCollector()
    # Record a tool call first so numeric claims are "verified"
    collector.record_llm_call(
        _make_messages(),
        "",
        [{"function": {"name": "search", "arguments": "{}"}}],
        _make_usage(),
        start_time=datetime.now(UTC),
    )
    content, tool_calls, result = guard_check(
        collector,
        "The GDP is $500 million",
        [],
        _make_messages(),
        _make_usage(),
        config,
        [HallucinationFlagEvaluator()],
        datetime.now(UTC),
    )
    assert not result.triggered


# ---------------------------------------------------------------------------
# Warn action
# ---------------------------------------------------------------------------


def test_guard_warn_appends_to_content() -> None:
    config = GuardConfig(
        rules=[
            GuardRule(evaluator_name="hallucination_flag", threshold=0.5, action=GuardAction.WARN),
        ]
    )
    collector = TraceCollector()
    # No prior tool calls → numeric claim is unverified → score 0.0
    content, tool_calls, result = guard_check(
        collector,
        "Revenue was $500 million last quarter",
        [],
        _make_messages(),
        _make_usage(),
        config,
        [HallucinationFlagEvaluator()],
        datetime.now(UTC),
    )
    assert result.triggered
    assert result.action_taken == GuardAction.WARN
    assert "[GUARD WARNING:" in content
    assert "Revenue was $500 million" in content  # original preserved


def test_guard_warn_custom_message() -> None:
    config = GuardConfig(
        rules=[
            GuardRule(
                evaluator_name="hallucination_flag",
                threshold=0.5,
                action=GuardAction.WARN,
                message="[CAUTION: verify numbers]",
            ),
        ]
    )
    collector = TraceCollector()
    content, _, result = guard_check(
        collector,
        "Growth was 47%",
        [],
        _make_messages(),
        _make_usage(),
        config,
        [HallucinationFlagEvaluator()],
        datetime.now(UTC),
    )
    assert result.triggered
    assert "[CAUTION: verify numbers]" in content


# ---------------------------------------------------------------------------
# Block action
# ---------------------------------------------------------------------------


def test_guard_block_replaces_content() -> None:
    config = GuardConfig(
        rules=[
            GuardRule(evaluator_name="policy_violation", threshold=1.0, action=GuardAction.BLOCK),
        ]
    )
    expected = TaskExpectation(policies=["forbidden phrase"])
    collector = TraceCollector()
    content, tool_calls, result = guard_check(
        collector,
        "This contains a forbidden phrase in the output",
        [],
        _make_messages(),
        _make_usage(),
        config,
        [PolicyViolationEvaluator()],
        datetime.now(UTC),
        expected=expected,
    )
    assert result.triggered
    assert result.action_taken == GuardAction.BLOCK
    assert "forbidden phrase" not in content.lower() or "reconsider" in content.lower()
    assert tool_calls == []


def test_guard_block_clears_tool_calls() -> None:
    config = GuardConfig(
        rules=[
            GuardRule(evaluator_name="policy_violation", threshold=1.0, action=GuardAction.BLOCK),
        ]
    )
    expected = TaskExpectation(policies=["secret"])
    collector = TraceCollector()
    original_tools = [{"function": {"name": "search", "arguments": '{"q": "secret data"}'}}]
    content, tool_calls, result = guard_check(
        collector,
        "Processing secret information",
        original_tools,
        _make_messages(),
        _make_usage(),
        config,
        [PolicyViolationEvaluator()],
        datetime.now(UTC),
        expected=expected,
    )
    assert result.triggered
    assert tool_calls == []


# ---------------------------------------------------------------------------
# Escalate action (sync — falls back to block without mailbox)
# ---------------------------------------------------------------------------


def test_guard_escalate_falls_back_to_block_without_mailbox() -> None:
    config = GuardConfig(
        rules=[
            GuardRule(evaluator_name="hallucination_flag", threshold=0.5, action=GuardAction.ESCALATE),
        ]
    )
    collector = TraceCollector()
    content, tool_calls, result = guard_check(
        collector,
        "Revenue was $999 billion",
        [],
        _make_messages(),
        _make_usage(),
        config,
        [HallucinationFlagEvaluator()],
        datetime.now(UTC),
    )
    assert result.triggered
    assert result.action_taken == GuardAction.ESCALATE
    assert tool_calls == []


# ---------------------------------------------------------------------------
# First-rule-wins behavior
# ---------------------------------------------------------------------------


def test_guard_first_matching_rule_wins() -> None:
    config = GuardConfig(
        rules=[
            GuardRule(evaluator_name="hallucination_flag", threshold=0.5, action=GuardAction.WARN),
            GuardRule(evaluator_name="hallucination_flag", threshold=0.5, action=GuardAction.BLOCK),
        ]
    )
    collector = TraceCollector()
    content, _, result = guard_check(
        collector,
        "The metric is 0.95",
        [],
        _make_messages(),
        _make_usage(),
        config,
        [HallucinationFlagEvaluator()],
        datetime.now(UTC),
    )
    assert result.triggered
    assert result.action_taken == GuardAction.WARN  # first rule, not block


# ---------------------------------------------------------------------------
# Loop detector integration
# ---------------------------------------------------------------------------


def test_guard_loop_detection() -> None:
    config = GuardConfig(
        rules=[
            GuardRule(evaluator_name="loop_detector", threshold=0.5, action=GuardAction.WARN),
        ]
    )
    collector = TraceCollector()
    # Record identical LLM calls to trigger loop detection
    for _ in range(3):
        collector.record_llm_call(
            _make_messages("same question"),
            "same answer",
            [],
            _make_usage(),
            start_time=datetime.now(UTC),
        )
    content, _, result = guard_check(
        collector,
        "same answer",
        [],
        _make_messages("same question"),
        _make_usage(),
        config,
        [LoopDetector()],
        datetime.now(UTC),
    )
    assert result.triggered
    assert result.action_taken == GuardAction.WARN
