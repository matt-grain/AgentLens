# Phase 1: Scaffold + Core Models

**Dependencies:** None
**Agent:** `python-fastapi`

## Overview

Initialize the project structure, define all Pydantic models, and create the manual Tracer for instrumentation.

## Files to Create

### `pyproject.toml`
**Purpose:** Project configuration with all dependencies
**Content:**
```toml
[project]
name = "agentlens"
version = "0.1.0"
description = "Trajectory-first agent evaluation framework"
requires-python = ">=3.13"
dependencies = [
    "pydantic>=2.0",
    "rich>=13.0.0",
    "typer[all]>=0.9.0",
    "jinja2>=3.1.0",
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
    "httpx>=0.27.0",
]

[project.optional-dependencies]
live = ["openai>=1.0.0"]

[dependency-groups]
dev = ["pytest>=8.0", "pytest-asyncio>=0.24", "ruff>=0.8.0", "pyright>=1.1.390"]

[project.scripts]
agentlens = "agentlens.cli:app"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/agentlens"]

[tool.ruff]
target-version = "py313"
line-length = 120

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM", "PTH"]

[tool.pyright]
pythonVersion = "3.13"
typeCheckingMode = "strict"
```

### `.python-version`
**Purpose:** Pin Python version for uv
**Content:** `3.13`

### `.gitignore` (ALREADY EXISTS)
**Note:** `.gitignore` already exists in the project with a comprehensive Python template. No changes needed.

### `CLAUDE.md`
**Purpose:** Project-specific instructions for Claude Code
**Content:**
```markdown
# AgentLens

Trajectory-first agent evaluation framework.

## Tech Stack
- Python 3.13, uv
- Pydantic 2.x for models
- FastAPI for proxy server
- Rich for terminal output
- Typer for CLI

## Architecture
- `src/agentlens/models/` — Pydantic models (Trace, Span, EvalResult, etc.)
- `src/agentlens/server/` — OpenAI-compatible proxy server
- `src/agentlens/evaluators/` — Pluggable evaluators (12 total)
- `src/agentlens/report/` — Terminal and HTML report generators
- `src/agentlens/cli.py` — Typer CLI entry point
- `demo/` — Research assistant agent and fixtures

## Patterns
- All models are frozen Pydantic BaseModel with `frozen=True`
- Evaluators implement the Evaluator Protocol (name, level, evaluate method)
- No LLM-as-judge — all evaluators are deterministic
- Proxy server auto-captures traces from LLM calls

## Commands
- `uv run agentlens demo` — Run demo with fixtures
- `uv run agentlens serve` — Start proxy server
- `uv run pytest` — Run tests
- `uv run ruff check src/` — Lint
- `uv run pyright .` — Type check
```

### `src/agentlens/__init__.py`
**Purpose:** Package init with public API exports
**Content:**
```python
"""AgentLens — Trajectory-first agent evaluation framework."""

from agentlens.models.trace import Span, SpanStatus, SpanType, TokenUsage, Trace
from agentlens.models.evaluation import EvalLevel, EvalResult, EvalSeverity, EvalSummary
from agentlens.models.expectation import TaskExpectation
from agentlens.capture.tracer import Tracer

__all__ = [
    "Span",
    "SpanStatus",
    "SpanType",
    "TokenUsage",
    "Trace",
    "EvalLevel",
    "EvalResult",
    "EvalSeverity",
    "EvalSummary",
    "TaskExpectation",
    "Tracer",
]
```

### `src/agentlens/py.typed`
**Purpose:** PEP 561 marker for typed package
**Content:** Empty file

### `src/agentlens/models/__init__.py`
**Purpose:** Models subpackage init
**Content:**
```python
"""Data models for traces and evaluations."""

from agentlens.models.trace import Span, SpanStatus, SpanType, TokenUsage, Trace
from agentlens.models.evaluation import EvalLevel, EvalResult, EvalSeverity, EvalSummary
from agentlens.models.expectation import TaskExpectation

__all__ = [
    "Span",
    "SpanStatus",
    "SpanType",
    "TokenUsage",
    "Trace",
    "EvalLevel",
    "EvalResult",
    "EvalSeverity",
    "EvalSummary",
    "TaskExpectation",
]
```

### `src/agentlens/models/trace.py`
**Purpose:** Core trace and span models for capturing agent execution
**Classes:**
- `SpanType(StrEnum)` — LLM_CALL, TOOL_CALL, DECISION, ERROR, ESCALATION
- `SpanStatus(StrEnum)` — SUCCESS, FAILURE, TIMEOUT
- `TokenUsage(BaseModel, frozen=True)` — input_tokens: int, output_tokens: int
- `Span(BaseModel, frozen=True)` — Individual step in agent execution
  - id: str
  - span_type: SpanType
  - name: str
  - input: dict[str, Any]
  - output: dict[str, Any] | None = None
  - status: SpanStatus = SpanStatus.SUCCESS
  - start_time: datetime
  - end_time: datetime
  - metadata: dict[str, Any] = Field(default_factory=dict)
  - parent_id: str | None = None
  - token_usage: TokenUsage | None = None
  - Property `duration_ms` → int (computed from start/end)
**Output key conventions (contract for evaluators):**
- LLM_CALL spans: `output={"content": "response text", "tool_calls": [...]}`
- TOOL_CALL spans: `output={"result": "tool output text"}`
- ERROR spans: `output={"error": "error message"}`
- ESCALATION spans: `output={"reason": "why escalated"}`
- DECISION spans: `output={"decision": "what was decided"}`
- `Trace(BaseModel)` — Complete agent execution record
  - id: str
  - task: str
  - agent_name: str
  - spans: list[Span]
  - final_output: str | None = None
  - started_at: datetime
  - completed_at: datetime
  - Property `total_tokens` → TokenUsage | None (sum of all spans)
  - Property `duration_ms` → int
**Constraints:**
- Use `from __future__ import annotations` for forward refs
- All datetime fields use `datetime` from stdlib (not pendulum)
- Use `Field(default_factory=dict)` for mutable defaults

### `src/agentlens/models/evaluation.py`
**Purpose:** Evaluation result models
**Classes:**
- `EvalLevel(StrEnum)` — BUSINESS, BEHAVIOR, RISK, OPERATIONAL
- `EvalSeverity(StrEnum)` — INFO, WARNING, CRITICAL
- `EvalResult(BaseModel, frozen=True)` — Single evaluator result
  - evaluator_name: str
  - level: EvalLevel
  - score: float (0.0 - 1.0)
  - passed: bool
  - message: str
  - severity: EvalSeverity
  - evidence: list[str] = Field(default_factory=list)
  - details: dict[str, Any] = Field(default_factory=dict)
- `EvalSummary(BaseModel)` — Aggregated evaluation results
  - trace_id: str
  - task: str
  - results: list[EvalResult]
  - level_scores: dict[EvalLevel, float]
  - overall_score: float
  - timestamp: datetime
  - Property `passed` → bool (all results passed)
  - Property `critical_failures` → list[EvalResult]

### `src/agentlens/models/expectation.py`
**Purpose:** Task expectations for evaluation comparison
**Classes:**
- `TaskExpectation(BaseModel, frozen=True)`
  - expected_output: str | None = None
  - expected_tools: list[str] = Field(default_factory=list)
  - forbidden_tools: list[str] = Field(default_factory=list)
  - max_steps: int | None = None
  - policies: list[str] = Field(default_factory=list)
  - expected_escalation: bool = False

### `src/agentlens/capture/__init__.py`
**Purpose:** Capture subpackage init
**Content:**
```python
"""Trace capture utilities."""

from agentlens.capture.tracer import Tracer

__all__ = ["Tracer"]
```

### `src/agentlens/capture/tracer.py`
**Purpose:** Manual instrumentation context manager for creating traces
**Classes:**
- `Tracer` — Context manager for building traces
  - `__init__(self, task: str, agent_name: str)` — Initialize with task description
  - `__enter__(self) -> Self` — Start trace, record started_at
  - `__exit__(...)` — End trace, record completed_at
  - `add_span(self, span_type: SpanType, name: str, input: dict, output: dict | None = None, ...) -> Span` — Add a span to the trace
  - `start_span(self, span_type: SpanType, name: str, input: dict, ...) -> SpanBuilder` — Start a span (returns builder for later completion)
  - `get_trace(self) -> Trace` — Get the completed trace
  - Property `trace_id` → str
**Helper class:**
- `SpanBuilder` — For spans that need start/end timing
  - `__init__(self, tracer: Tracer, span_type: SpanType, name: str, input: dict, ...)`
  - `complete(self, output: dict | None = None, status: SpanStatus = SpanStatus.SUCCESS) -> Span`
**Constraints:**
- Generate trace/span IDs with `uuid.uuid4().hex[:12]`
- Use `datetime.now(UTC)` for timestamps
- Tracer is NOT thread-safe (single-threaded usage expected)

## Test Files to Create

### `tests/__init__.py`
**Purpose:** Test package init
**Content:** Empty file

### `tests/conftest.py`
**Purpose:** Shared pytest fixtures
**Fixtures:**
- `sample_span() -> Span` — A basic LLM_CALL span
- `sample_trace() -> Trace` — A trace with 3 spans (llm, tool, llm)
- `sample_expectation() -> TaskExpectation` — Basic expectation with expected_tools
**Pattern:** Use `@pytest.fixture` decorator, return fully constructed objects

### `tests/test_models.py`
**Purpose:** Test Pydantic models
**Tests:**
- `test_span_duration_ms_computed_correctly` — Verify duration property
- `test_span_frozen_raises_on_mutation` — Verify immutability
- `test_trace_total_tokens_sums_spans` — Verify token aggregation
- `test_trace_duration_ms_computed_correctly` — Verify trace duration
- `test_eval_result_frozen` — Verify immutability
- `test_eval_summary_passed_property` — True when all pass, False otherwise
- `test_eval_summary_critical_failures` — Filters to critical severity
- `test_task_expectation_defaults` — Verify default values

### `tests/test_tracer.py`
**Purpose:** Test Tracer context manager
**Tests:**
- `test_tracer_creates_trace_with_task_and_agent` — Basic creation
- `test_tracer_records_timestamps` — started_at and completed_at set
- `test_tracer_add_span_appends_to_trace` — Spans added correctly
- `test_tracer_start_span_and_complete` — SpanBuilder workflow
- `test_tracer_generates_unique_ids` — IDs are unique across calls
- `test_tracer_context_manager_usage` — with statement works

## Verification

After implementation:
1. `uv sync` — Install deps
2. `uv run pytest tests/` — All tests pass
3. `uv run ruff check src/` — No lint errors
4. `uv run pyright .` — Type check passes
