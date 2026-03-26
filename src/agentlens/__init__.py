"""AgentLens — Trajectory-first agent evaluation framework."""

from __future__ import annotations

from agentlens.capture.tracer import Tracer
from agentlens.engine import EvaluationSuite
from agentlens.evaluators import Evaluator
from agentlens.models.evaluation import EvalLevel, EvalResult, EvalSeverity, EvalSummary
from agentlens.models.expectation import TaskExpectation
from agentlens.models.trace import Span, SpanStatus, SpanType, TokenUsage, Trace
from agentlens.report import generate_html_report, print_report

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "EvalLevel",
    "EvalResult",
    "EvalSeverity",
    "EvalSummary",
    "EvaluationSuite",
    "Evaluator",
    "Span",
    "SpanStatus",
    "SpanType",
    "TaskExpectation",
    "TokenUsage",
    "Trace",
    "Tracer",
    "generate_html_report",
    "print_report",
]
