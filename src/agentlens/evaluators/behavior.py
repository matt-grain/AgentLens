"""Behavior-level evaluators for tool use, efficiency, loops, and recovery."""

from __future__ import annotations

import hashlib
import json

from agentlens.models.evaluation import EvalLevel, EvalResult, EvalSeverity
from agentlens.models.expectation import TaskExpectation
from agentlens.models.trace import Span, SpanStatus, SpanType, Trace


class ToolSelectionEvaluator:
    """Checks whether the agent used expected tools and avoided forbidden ones."""

    name: str = "tool_selection"
    level: EvalLevel = EvalLevel.BEHAVIOR

    def evaluate(self, trace: Trace, expected: TaskExpectation | None = None) -> list[EvalResult]:
        tool_names = {s.name for s in trace.spans if s.span_type == SpanType.TOOL_CALL}
        score, evidence = self._score(tool_names, expected)

        message = "Tool selection is optimal." if score == 1.0 else f"Tool selection issues: {'; '.join(evidence)}"
        return [
            EvalResult(
                evaluator_name=self.name,
                level=self.level,
                score=score,
                passed=score > 0.5,
                message=message,
                severity=EvalSeverity.INFO if score > 0.5 else EvalSeverity.WARNING,
                evidence=evidence,
            )
        ]

    def _score(self, tool_names: set[str], expected: TaskExpectation | None) -> tuple[float, list[str]]:
        if expected is None:
            return 1.0, []

        evidence: list[str] = []
        expected_tools = expected.expected_tools
        forbidden_tools = expected.forbidden_tools

        if expected_tools:
            used = [t for t in expected_tools if t in tool_names]
            expected_score = len(used) / len(expected_tools)
            missing = [t for t in expected_tools if t not in tool_names]
            if missing:
                evidence.append(f"Missing expected tools: {missing}")
        else:
            expected_score = 1.0

        if forbidden_tools:
            used_forbidden = [t for t in forbidden_tools if t in tool_names]
            forbidden_score = 1.0 - len(used_forbidden) / len(forbidden_tools)
            if used_forbidden:
                evidence.append(f"Used forbidden tools: {used_forbidden}")
        else:
            forbidden_score = 1.0

        # Forbidden tool use is a hard failure regardless of expected score
        return expected_score * 0.5 + forbidden_score * 0.5, evidence


class StepEfficiencyEvaluator:
    """Evaluates whether the agent completed the task in a reasonable number of steps."""

    name: str = "step_efficiency"
    level: EvalLevel = EvalLevel.BEHAVIOR

    def evaluate(self, trace: Trace, expected: TaskExpectation | None = None) -> list[EvalResult]:
        actual = len(trace.spans)
        score, message = self._score(actual, expected)

        return [
            EvalResult(
                evaluator_name=self.name,
                level=self.level,
                score=score,
                passed=score >= 0.7,
                message=message,
                severity=EvalSeverity.INFO if score >= 0.7 else EvalSeverity.WARNING,
                details={"actual_steps": actual},
            )
        ]

    def _score(self, actual: int, expected: TaskExpectation | None) -> tuple[float, str]:
        max_steps = expected.max_steps if expected else None
        if max_steps is not None:
            if actual <= max_steps:
                return 1.0, f"Completed in {actual}/{max_steps} steps."
            score = max(0.0, 1.0 - (actual - max_steps) / max_steps)
            return score, f"Exceeded step limit: {actual} steps (max {max_steps})."
        if actual <= 10:
            return 1.0, f"Efficient: {actual} steps."
        score = max(0.5, 1.0 - (actual - 10) / 20)
        return score, f"High step count: {actual} steps."


class LoopDetector:
    """Detects repeated or cyclical patterns in agent execution — the signature evaluator."""

    name: str = "loop_detector"
    level: EvalLevel = EvalLevel.BEHAVIOR

    def evaluate(self, trace: Trace, expected: TaskExpectation | None = None) -> list[EvalResult]:
        fps = [self._fingerprint(s) for s in trace.spans]
        dups = sum(1 for i in range(1, len(fps)) if fps[i] == fps[i - 1])
        has_cycle = self._detect_cycle(fps)
        score, severity, message = self._classify(dups, has_cycle)
        return [
            EvalResult(
                evaluator_name=self.name,
                level=self.level,
                score=score,
                passed=score >= 0.5,
                message=message,
                severity=severity,
                details={"consecutive_duplicates": dups, "cycle_detected": has_cycle},
            )
        ]

    def _fingerprint(self, span: Span) -> tuple[str, str, str]:
        h = hashlib.md5(  # noqa: S324  # MD5 for non-crypto fingerprinting
            json.dumps(span.input, sort_keys=True).encode(), usedforsecurity=False
        ).hexdigest()[:8]
        return (span.span_type, span.name, h)

    def _detect_cycle(self, fps: list[tuple[str, str, str]]) -> bool:
        # Non-consecutive recurrence (A -> B -> A). Consecutive dups counted separately.
        seen: set[tuple[str, str, str]] = set()
        prev: tuple[str, str, str] | None = None
        for fp in fps:
            if fp != prev and fp in seen:
                return True
            seen.add(fp)
            prev = fp
        return False

    def _classify(self, dups: int, has_cycle: bool) -> tuple[float, EvalSeverity, str]:
        if has_cycle:
            return 0.0, EvalSeverity.CRITICAL, "Execution cycle detected — agent is looping."
        if dups >= 2:
            return 0.3, EvalSeverity.WARNING, f"Multiple consecutive duplicate steps ({dups})."
        if dups == 1:
            return 0.7, EvalSeverity.WARNING, "One consecutive duplicate step detected."
        return 1.0, EvalSeverity.INFO, "No loops or duplicate steps detected."


class RecoveryEvaluator:
    """Checks whether the agent recovered from failures."""

    name: str = "recovery"
    level: EvalLevel = EvalLevel.BEHAVIOR

    def evaluate(self, trace: Trace, expected: TaskExpectation | None = None) -> list[EvalResult]:
        failure_indices = [i for i, s in enumerate(trace.spans) if s.status == SpanStatus.FAILURE]

        if not failure_indices:
            return [
                EvalResult(
                    evaluator_name=self.name,
                    level=self.level,
                    score=1.0,
                    passed=True,
                    message="No failures encountered.",
                    severity=EvalSeverity.INFO,
                )
            ]

        recovered = self._count_recoveries(trace, failure_indices)
        score, message = self._score(recovered, len(failure_indices))

        return [
            EvalResult(
                evaluator_name=self.name,
                level=self.level,
                score=score,
                passed=score >= 0.5,
                message=message,
                severity=EvalSeverity.INFO if score >= 0.5 else EvalSeverity.WARNING,
                details={"failures": len(failure_indices), "recovered": recovered},
            )
        ]

    def _count_recoveries(self, trace: Trace, failure_indices: list[int]) -> int:
        count = 0
        for idx in failure_indices:
            next_idx = idx + 1
            if next_idx < len(trace.spans) and trace.spans[next_idx].name != trace.spans[idx].name:
                count += 1
        return count

    def _score(self, recovered: int, total_failures: int) -> tuple[float, str]:
        if recovered == total_failures:
            return 1.0, f"Recovered from all {total_failures} failure(s)."
        if recovered > 0:
            return 0.5, f"Partially recovered: {recovered}/{total_failures} failures."
        return 0.0, f"No recovery attempts after {total_failures} failure(s)."
