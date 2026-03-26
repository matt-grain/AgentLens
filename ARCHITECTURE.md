# Architecture

## Overview

AgentLens is a trajectory-first agent evaluation framework. It captures the full sequence of LLM calls and tool invocations that an agent makes (its trajectory), then runs 12 deterministic evaluators across four levels — Business, Behavior, Risk, and Operational — to produce a scored report. Traces can be captured automatically via an OpenAI-compatible proxy server, recorded manually via the `Tracer` context manager, or loaded from JSON fixtures.

## Tech Stack

| Component | Library | Version |
|-----------|---------|---------|
| Language | Python | 3.13 |
| Data models | Pydantic | 2.x |
| Proxy server | FastAPI + uvicorn | 0.115+ |
| Terminal output | Rich | 13+ |
| HTML templates | Jinja2 | 3.1+ |
| CLI | Typer | 0.9+ |
| HTTP client (proxy) | httpx | 0.27+ |

## Project Structure

```
src/agentlens/
├── __init__.py          # Public API surface — re-exports key symbols
├── cli.py               # Typer CLI: demo, evaluate, serve commands
├── engine.py            # EvaluationSuite — orchestrates evaluators
├── models/
│   ├── trace.py         # Trace, Span, SpanType, SpanStatus, TokenUsage
│   ├── evaluation.py    # EvalResult, EvalSummary, EvalLevel, EvalSeverity
│   └── expectation.py   # TaskExpectation — per-scenario ground truth
├── evaluators/
│   ├── __init__.py      # Evaluator Protocol + default_evaluators()
│   ├── business.py      # TaskCompletion, HumanHandoff
│   ├── behavior.py      # ToolSelection, StepEfficiency, LoopDetector, Recovery
│   ├── risk.py          # UnauthorizedAction, HallucinationFlag, PolicyViolation
│   └── operational.py   # Latency, Cost, Variance
├── server/
│   ├── proxy.py         # FastAPI app factory (create_app)
│   ├── canned.py        # CannedRegistry + per-scenario mock responses
│   └── models.py        # OpenAI-compatible request/response Pydantic models
├── report/
│   ├── terminal.py      # Rich-based terminal report (print_report)
│   └── html.py          # Jinja2 HTML report (generate_html_report)
└── capture/
    └── tracer.py        # Tracer context manager + SpanBuilder

demo/
├── scenarios.py         # SCENARIOS registry + load_scenario()
├── agent.py             # Research assistant agent (live mode)
└── fixtures/
    ├── happy_path.json  # Pre-recorded trace — clean execution
    ├── loop_scenario.json   # Pre-recorded trace — repeated tool calls
    └── risk_scenario.json   # Pre-recorded trace — unauthorized action

tests/
├── conftest.py          # Shared fixtures (sample_trace, sample_span, etc.)
├── test_models.py       # Pydantic model validation
├── test_engine.py       # EvaluationSuite unit tests
├── test_evaluators/     # Per-evaluator unit tests
├── test_server.py       # FastAPI integration tests via TestClient
├── test_report.py       # Terminal + HTML report smoke tests
├── test_tracer.py       # Tracer + SpanBuilder unit tests
├── test_cli.py          # CLI command tests via subprocess
└── test_e2e.py          # End-to-end scenario tests
```

## Layer Responsibilities

### models/
**Does:** Define the data shapes that flow through the system. All models are frozen Pydantic `BaseModel` instances with `frozen=True`.

**Must NOT:** Contain any business logic, I/O, or evaluation logic.

```python
class Trace(BaseModel, frozen=True):
    id: str
    task: str
    agent_name: str
    spans: list[Span]
    started_at: datetime
    completed_at: datetime
    final_output: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
```

### evaluators/
**Does:** Implement the `Evaluator` protocol. Each evaluator receives a `Trace` and optional `TaskExpectation`, and returns a list of `EvalResult` objects. All evaluators are stateless and deterministic.

**Must NOT:** Make network calls, mutate models, or depend on other evaluators.

```python
class Evaluator(Protocol):
    name: str
    level: EvalLevel

    def evaluate(self, trace: Trace, expected: TaskExpectation | None = None) -> list[EvalResult]:
        ...
```

### engine/
**Does:** `EvaluationSuite` collects evaluators, runs them over a trace, and aggregates level scores into a weighted overall score.

**Must NOT:** Know about rendering, CLI concerns, or server state.

### server/
**Does:** Expose OpenAI-compatible endpoints (`/v1/chat/completions`), capture spans into an in-memory trace, and finalize traces on `/traces/reset`. `create_app()` is a factory that wires closures for state.

**Must NOT:** Run evaluators, render reports, or touch the file system.

```python
def create_app(
    mode: Literal["mock", "proxy"] = "mock",
    proxy_target: str | None = None,
    scenario: str = "happy_path",
) -> FastAPI: ...
```

### report/
**Does:** Render `EvalSummary` + `Trace` to Rich terminal output or Jinja2 HTML. Pure rendering — no evaluation logic.

**Must NOT:** Call evaluators, read files, or make network requests.

### cli.py
**Does:** Wire together the engine, report, and server for user-facing commands via Typer.

**Must NOT:** Contain business logic beyond argument parsing and orchestration.

## Data Flow

A typical fixture-based evaluation:

```
1. load_scenario("happy_path")
      -> reads demo/fixtures/happy_path.json
      -> returns (Trace, TaskExpectation)

2. EvaluationSuite().evaluate(trace, expected)
      -> runs 12 Evaluator.evaluate() calls
      -> _compute_level_scores() averages per EvalLevel
      -> _compute_overall_score() applies weights
      -> returns EvalSummary

3. print_report(summary, trace)
      -> Rich Console renders level table + trajectory timeline

4. (optional) generate_html_report(summary, trace, path)
      -> Jinja2 renders HTML to disk
```

A typical proxy-captured evaluation:

```
1. Agent sets OPENAI_API_BASE=http://localhost:8650/v1

2. Agent calls openai.chat.completions.create(...)
      -> AgentLens proxy receives POST /v1/chat/completions
      -> Returns canned (mock) or proxied (live) response
      -> Appends LLM span + tool spans to current_spans[]

3. POST /traces/reset
      -> _finalize_trace() packages current_spans[] into a Trace
      -> Appends Trace to traces[]

4. GET /traces -> returns list of finalized Trace dicts
```

## Key Patterns

### Evaluator Protocol

Every evaluator is a plain class that satisfies the structural `Evaluator` protocol. No inheritance required — duck typing via `Protocol`.

```python
class LoopDetector:
    name = "loop_detector"
    level = EvalLevel.BEHAVIOR

    def evaluate(self, trace: Trace, expected: TaskExpectation | None = None) -> list[EvalResult]:
        tool_calls = [s for s in trace.spans if s.span_type == SpanType.TOOL_CALL]
        names = [s.name for s in tool_calls]
        # detect 3+ identical consecutive tool calls
        ...
```

### Canned Response Registry

`CannedRegistry` holds ordered response sequences per scenario name. Each call to `next_response(scenario)` advances the index cyclically, simulating a multi-turn agent conversation without hitting real APIs.

```python
REGISTRY = CannedRegistry()
REGISTRY.register("happy_path", [
    CannedResponse(content="I'll search for France and Germany GDP data."),
    CannedResponse(content="", tool_calls=[...]),
    ...
])
```

### Trace Capture in Proxy

The proxy uses closure-captured mutable containers (`current_spans: list[Span]`, `traces: list[Trace]`) within `create_app()`. This is an intentional design choice: it keeps the server stateless from FastAPI's perspective while supporting simple single-agent-at-a-time trace capture.

```python
def create_app(...) -> FastAPI:
    traces: list[Trace] = []
    current_spans: list[Span] = []

    @app.post("/v1/chat/completions")
    async def chat_completions(request: ChatCompletionRequest) -> dict[str, Any]:
        # build spans, append to current_spans
        ...

    @app.post("/traces/reset")
    async def reset_traces() -> dict[str, str]:
        _finalize_trace(current_spans, current_task[0], traces)
        current_spans.clear()
        ...
```

## Design Decisions

See [decisions.md](decisions.md) for the full Architecture Decision Records.

Key decisions at a glance:
- Proxy server over SDK wrappers — provider-agnostic by design
- All evaluators are deterministic — no LLM-as-judge
- Pre-recorded fixtures for the demo — zero-friction, no API keys
- Single trace per proxy session — kept simple intentionally
