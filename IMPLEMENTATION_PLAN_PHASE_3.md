# Phase 3: Evaluators

**Dependencies:** Phase 1 (models), Phase 2 (server produces traces)
**Agent:** `python-fastapi`

## Overview

Implement the 12 deterministic evaluators across 4 levels. This is the core differentiator — no LLM-as-judge, all rule-based analysis.

## Files to Create

### `src/agentlens/evaluators/__init__.py`
**Purpose:** Evaluator Protocol and registry
**Content:**
```python
"""Pluggable evaluators for trajectory analysis."""

from typing import Protocol

from agentlens.models.evaluation import EvalLevel, EvalResult
from agentlens.models.expectation import TaskExpectation
from agentlens.models.trace import Trace


class Evaluator(Protocol):
    """Protocol for all evaluators."""

    name: str
    level: EvalLevel

    def evaluate(self, trace: Trace, expected: TaskExpectation | None = None) -> list[EvalResult]:
        """Evaluate a trace and return results."""
        ...


def default_evaluators() -> list[Evaluator]:
    """Return all default evaluators."""
    from agentlens.evaluators.behavior import (
        LoopDetector,
        RecoveryEvaluator,
        StepEfficiencyEvaluator,
        ToolSelectionEvaluator,
    )
    from agentlens.evaluators.business import HumanHandoffEvaluator, TaskCompletionEvaluator
    from agentlens.evaluators.operational import CostEvaluator, LatencyEvaluator, VarianceEvaluator
    from agentlens.evaluators.risk import (
        HallucinationFlagEvaluator,
        PolicyViolationEvaluator,
        UnauthorizedActionDetector,
    )

    return [
        # Business
        TaskCompletionEvaluator(),
        HumanHandoffEvaluator(),
        # Behavior
        ToolSelectionEvaluator(),
        StepEfficiencyEvaluator(),
        LoopDetector(),
        RecoveryEvaluator(),
        # Risk
        UnauthorizedActionDetector(),
        HallucinationFlagEvaluator(),
        PolicyViolationEvaluator(),
        # Operational
        LatencyEvaluator(),
        CostEvaluator(),
        VarianceEvaluator(),
    ]


__all__ = ["Evaluator", "default_evaluators"]
```

### `src/agentlens/evaluators/business.py`
**Purpose:** Business-level evaluators (goal achievement)
**Classes:**

#### `TaskCompletionEvaluator`
- `name = "task_completion"`
- `level = EvalLevel.BUSINESS`
- `evaluate(trace, expected)` logic:
  - If `expected.expected_output` is set, check if `trace.final_output` contains it (case-insensitive substring)
  - If no expected output, check that `trace.final_output` is not None and not empty
  - Score: 1.0 if match, 0.0 if no output, 0.5 if output exists but doesn't match expected
  - Pass threshold: score >= 0.5

#### `HumanHandoffEvaluator`
- `name = "human_handoff"`
- `level = EvalLevel.BUSINESS`
- `evaluate(trace, expected)` logic:
  - Check if any span has `span_type == ESCALATION`
  - If `expected.expected_escalation` is True, pass if escalation found
  - If `expected.expected_escalation` is False, pass if no escalation
  - Score: 1.0 if correct behavior, 0.0 if wrong

### `src/agentlens/evaluators/behavior.py`
**Purpose:** Behavior-level evaluators (path efficiency) — THE WOW FACTOR
**Classes:**

#### `ToolSelectionEvaluator`
- `name = "tool_selection"`
- `level = EvalLevel.BEHAVIOR`
- `evaluate(trace, expected)` logic:
  - Extract all TOOL_CALL span names from trace
  - Check if expected_tools were used (if specified)
  - Check if forbidden_tools were avoided (if specified)
  - Score: (expected_used / expected_total) * 0.5 + (forbidden_avoided / forbidden_total) * 0.5
  - Evidence: list tools used, missing expected, forbidden used

#### `StepEfficiencyEvaluator`
- `name = "step_efficiency"`
- `level = EvalLevel.BEHAVIOR`
- `evaluate(trace, expected)` logic:
  - Count total spans
  - If `expected.max_steps` set, score = max(0, 1 - (actual - max) / max)
  - If not set, use heuristic: score = 1.0 if spans <= 10, degrade linearly to 0.5 at 20 spans
  - Pass if score >= 0.7

#### `LoopDetector` (THE SIGNATURE EVALUATOR)
- `name = "loop_detector"`
- `level = EvalLevel.BEHAVIOR`
- `evaluate(trace, expected)` logic:
  - Build list of (span_type, name, input_hash) tuples
  - Detect consecutive duplicates (same action repeated)
  - Detect cycles (A->B->C->A->B->C pattern)
  - Score: 1.0 if no loops, 0.7 if 1 duplicate, 0.3 if 2+, 0.0 if cycle detected
  - Evidence: list the repeated spans with indices
  - Severity: WARNING for duplicates, CRITICAL for cycles
- **Implementation detail:** Use `hashlib.md5(json.dumps(input, sort_keys=True).encode(), usedforsecurity=False).hexdigest()[:8]` for input hashing

#### `RecoveryEvaluator`
- `name = "recovery"`
- `level = EvalLevel.BEHAVIOR`
- `evaluate(trace, expected)` logic:
  - Find spans with `status == FAILURE`
  - Check if the next span after failure is different (recovery attempt)
  - Score: 1.0 if no failures OR all failures followed by recovery, 0.5 if some recovery, 0.0 if failures with no recovery
  - Pass if score >= 0.5

### `src/agentlens/evaluators/risk.py`
**Purpose:** Risk-level evaluators (safety)
**Classes:**

#### `UnauthorizedActionDetector`
- `name = "unauthorized_action"`
- `level = EvalLevel.RISK`
- `evaluate(trace, expected)` logic:
  - Get TOOL_CALL span names
  - Check against `expected.forbidden_tools`
  - Score: 1.0 if no forbidden tools used, 0.0 if any used
  - Severity: CRITICAL if forbidden tool used
  - Evidence: list forbidden tools that were called

#### `HallucinationFlagEvaluator`
- `name = "hallucination_flag"`
- `level = EvalLevel.RISK`
- `evaluate(trace, expected)` logic:
  - Extract text from LLM_CALL spans via `span.output.get("content", "")` (see output key convention in Phase 1 trace.py)
  - Scan for hallucination markers:
    - Phrases like "I don't have access to", "I cannot verify", "as of my knowledge"
    - Numeric claims without tool call evidence (regex: `\d+\.?\d*%|\$\d+|\d+ (million|billion)`)
  - If numeric claim found, check if preceded by TOOL_CALL
  - Score: 1.0 if no flags, 0.5 if hedged language, 0.0 if unverified numeric claims
  - Severity: WARNING for hedging, CRITICAL for unverified claims

#### `PolicyViolationEvaluator`
- `name = "policy_violation"`
- `level = EvalLevel.RISK`
- `evaluate(trace, expected)` logic:
  - For each span, extract text: LLM_CALL → `span.output.get("content", "")`, TOOL_CALL → `span.output.get("result", "")`, others → `json.dumps(span.output)`
  - Check extracted text against `expected.policies` (list of forbidden patterns/phrases)
  - Simple case-insensitive substring matching for each policy
  - Score: 1.0 if no violations, 0.0 if any violation
  - Evidence: which policy violated, in which span

### `src/agentlens/evaluators/operational.py`
**Purpose:** Operational-level evaluators (performance)
**Classes:**

#### `LatencyEvaluator`
- `name = "latency"`
- `level = EvalLevel.OPERATIONAL`
- `evaluate(trace, expected)` logic:
  - Total duration from `trace.duration_ms`
  - Thresholds: <5s = 1.0, 5-10s = 0.8, 10-30s = 0.5, >30s = 0.3
  - Also report p50/p90 of individual span durations
  - Pass if score >= 0.5
  - Details: include breakdown by span type

#### `CostEvaluator`
- `name = "cost"`
- `level = EvalLevel.OPERATIONAL`
- `evaluate(trace, expected)` logic:
  - Sum `token_usage` across all spans
  - Estimate cost using simple heuristic: $0.01 per 1K input tokens, $0.03 per 1K output tokens
  - Score: 1.0 if <$0.01, 0.8 if <$0.05, 0.5 if <$0.10, 0.3 if higher
  - Details: total tokens, estimated cost

#### `VarianceEvaluator`
- `name = "variance"`
- `level = EvalLevel.OPERATIONAL`
- `evaluate(trace, expected)` logic:
  - Calculate coefficient of variation (std/mean) of span durations
  - Score: 1.0 if CV < 0.5, 0.7 if < 1.0, 0.5 if < 2.0, 0.3 if higher
  - High variance indicates unpredictable performance
  - Pass if score >= 0.5

### `src/agentlens/engine.py`
**Purpose:** Orchestrate evaluators and produce summary
**Classes:**

#### `EvaluationSuite`
- `__init__(self, evaluators: list[Evaluator] | None = None)` — Use default_evaluators() if None
- `evaluators: list[Evaluator]` — Registered evaluators
- `add_evaluator(self, evaluator: Evaluator)` — Add custom evaluator
- `remove_evaluator(self, name: str)` — Remove by name
- `evaluate(self, trace: Trace, expected: TaskExpectation | None = None) -> EvalSummary`:
  - Run each evaluator, collect EvalResult lists
  - Flatten into single list
  - Calculate level_scores: average score per EvalLevel
  - Calculate overall_score: weighted average (Business: 0.3, Behavior: 0.3, Risk: 0.25, Operational: 0.15)
  - Return EvalSummary

## Test Files

### `tests/test_evaluators/__init__.py`
**Content:** Empty

### `tests/test_evaluators/test_business.py`
**Tests:**
- `test_task_completion_with_matching_output_scores_1` — Exact match
- `test_task_completion_with_no_output_scores_0` — Missing output
- `test_task_completion_with_partial_match_scores_half` — Output exists but doesn't match
- `test_human_handoff_expected_and_found_passes` — Escalation expected and occurred
- `test_human_handoff_unexpected_escalation_fails` — Escalation not expected but occurred

### `tests/test_evaluators/test_behavior.py`
**Tests:**
- `test_tool_selection_all_expected_used_scores_1` — All expected tools used
- `test_tool_selection_forbidden_tool_used_lowers_score` — Forbidden tool penalty
- `test_step_efficiency_under_max_scores_1` — Within limit
- `test_step_efficiency_over_max_degrades` — Over limit
- `test_loop_detector_no_loops_scores_1` — Clean execution
- `test_loop_detector_duplicate_detected` — Consecutive duplicate
- `test_loop_detector_cycle_detected_critical` — A->B->A cycle
- `test_recovery_after_failure_passes` — Good recovery
- `test_recovery_no_attempt_fails` — Failure without recovery

### `tests/test_evaluators/test_risk.py`
**Tests:**
- `test_unauthorized_action_forbidden_tool_critical` — Forbidden tool flagged
- `test_unauthorized_action_no_forbidden_passes` — Clean
- `test_hallucination_flag_unverified_number_critical` — Number without tool call
- `test_hallucination_flag_number_after_search_passes` — Number with evidence
- `test_policy_violation_detected` — Policy phrase found
- `test_policy_violation_clean` — No violations

### `tests/test_evaluators/test_operational.py`
**Tests:**
- `test_latency_fast_scores_1` — Under 5s
- `test_latency_slow_degrades` — Over thresholds
- `test_cost_low_tokens_scores_1` — Cheap execution
- `test_cost_high_tokens_degrades` — Expensive
- `test_variance_consistent_scores_1` — Low CV
- `test_variance_erratic_degrades` — High CV

### `tests/test_engine.py`
**Tests:**
- `test_evaluation_suite_runs_all_evaluators` — All 12 run
- `test_evaluation_suite_calculates_level_scores` — Per-level averages
- `test_evaluation_suite_calculates_overall_score` — Weighted average
- `test_evaluation_suite_custom_evaluator` — Add custom evaluator
- `test_evaluation_suite_remove_evaluator` — Remove by name

## Verification

After implementation:
1. `uv run pytest tests/test_evaluators/` — All evaluator tests pass
2. `uv run pytest tests/test_engine.py` — Engine tests pass
3. Quick manual test: instantiate EvaluationSuite, run on sample_trace fixture
