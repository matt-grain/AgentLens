"""Business-level evaluators for task completion and escalation."""

from __future__ import annotations

from agentlens.models.evaluation import EvalLevel, EvalResult, EvalSeverity
from agentlens.models.expectation import TaskExpectation
from agentlens.models.trace import SpanType, Trace


class TaskCompletionEvaluator:
    """Checks whether the agent completed the assigned task."""

    name: str = "task_completion"
    level: EvalLevel = EvalLevel.BUSINESS

    def evaluate(self, trace: Trace, expected: TaskExpectation | None = None) -> list[EvalResult]:
        score, message = self._score(trace, expected)
        return [
            EvalResult(
                evaluator_name=self.name,
                level=self.level,
                score=score,
                passed=score >= 0.5,
                message=message,
                severity=EvalSeverity.INFO if score >= 0.5 else EvalSeverity.WARNING,
            )
        ]

    def _score(self, trace: Trace, expected: TaskExpectation | None) -> tuple[float, str]:
        if not trace.final_output:
            return 0.0, "No final output produced."

        if expected is None or expected.expected_output is None:
            return 1.0, "Task completed with output."

        expected_text = expected.expected_output.lower()
        actual_text = trace.final_output.lower()

        if expected_text in actual_text:
            return 1.0, "Output matches expected result."

        return 0.5, "Output exists but does not match expected result."


class HumanHandoffEvaluator:
    """Checks whether escalation to a human occurred as expected."""

    name: str = "human_handoff"
    level: EvalLevel = EvalLevel.BUSINESS

    def evaluate(self, trace: Trace, expected: TaskExpectation | None = None) -> list[EvalResult]:
        escalated = any(s.span_type == SpanType.ESCALATION for s in trace.spans)
        expected_escalation = expected.expected_escalation if expected else False

        correct = escalated == expected_escalation
        score = 1.0 if correct else 0.0

        if correct and escalated:
            message = "Correctly escalated to human."
        elif correct and not escalated:
            message = "Correctly handled without escalation."
        elif escalated:
            message = "Unexpected escalation to human."
        else:
            message = "Expected escalation did not occur."

        return [
            EvalResult(
                evaluator_name=self.name,
                level=self.level,
                score=score,
                passed=correct,
                message=message,
                severity=EvalSeverity.INFO if correct else EvalSeverity.WARNING,
            )
        ]
