# Phase 5: Polish

**Dependencies:** Phase 1-4 (all code complete)
**Agent:** `general-purpose`

## Overview

Documentation, public API cleanup, and end-to-end testing. Make the project portfolio-ready.

## Files to Create/Update

### `README.md`
**Purpose:** Project landing page — first thing interviewers see
**Sections:**
1. **Header** — Name, one-line description, badges (Python 3.13, License)
2. **The Problem** — 2-3 sentences on why trajectory evaluation matters
3. **Quick Start** — 4 commands to run demo
4. **Architecture Diagram** — ASCII art from SPECS.md
5. **4-Level Framework Table** — Level, What It Measures, Evaluators
6. **Demo Output** — Screenshot or code block of terminal output
7. **CLI Commands** — All commands with examples
8. **Writing Custom Evaluators** — 10-line example
9. **Integration** — How to point any agent at the proxy
10. **Why AgentLens** — Differentiators (vs RAGAS, DeepEval)

**Constraints:**
- Under 300 lines
- No emojis in headers
- Include install command: `uv add agentlens` (once published) or `uv pip install -e .`

### `ARCHITECTURE.md`
**Purpose:** Technical deep-dive for serious reviewers
**Sections:**
1. **Overview** — One paragraph
2. **Tech Stack** — Python 3.13, Pydantic, FastAPI, Rich, Typer, Jinja2
3. **Project Structure** — Tree with descriptions
4. **Layer Responsibilities**
   - models/ — Pydantic models, frozen, serializable
   - server/ — OpenAI-compatible proxy, trace capture
   - evaluators/ — Protocol-based, deterministic, pluggable
   - report/ — Terminal and HTML output
   - cli.py — Typer entry point
5. **Data Flow** — Request lifecycle through proxy → trace → evaluate → report
6. **Key Patterns**
   - Evaluator Protocol (show code)
   - Trace capture in proxy (show code)
   - Canned response registry (show code)
7. **Design Decisions** — Link to decisions.md

### `decisions.md`
**Purpose:** Architecture Decision Records
**ADRs to include:**

#### 2026-03-26 — OpenAI-Compatible Proxy Over SDK Wrappers
**Status:** accepted
**Context:** Need provider abstraction without vendor lock-in
**Decision:** Build OpenAI-compatible proxy server instead of SDK wrappers or LiteLLM
**Alternatives:** LiteLLM (compromised March 2026), SDK wrappers (one per provider), OpenTelemetry (too heavy)
**Consequences:** Any framework works via OPENAI_API_BASE, but requires running proxy server

#### 2026-03-26 — Deterministic Evaluators Over LLM-as-Judge
**Status:** accepted
**Context:** Need reliable, reproducible evaluations
**Decision:** All 12 evaluators are rule-based, no LLM calls
**Alternatives:** LLM-as-judge (non-deterministic, costly), hybrid (complexity)
**Consequences:** Evaluations are instant, free, reproducible, but may miss nuanced issues

#### 2026-03-26 — Pre-Recorded Fixtures as Default Demo
**Status:** accepted
**Context:** Demo must run instantly without API keys
**Decision:** Ship pre-recorded trace JSON files, use `--live` flag for real execution
**Alternatives:** Always-live (requires setup), mock-only (less impressive)
**Consequences:** Zero-friction demo, but fixtures may drift from real behavior

#### 2026-03-26 — Single Trace Per Proxy Session
**Status:** accepted
**Context:** Need to associate spans with traces
**Decision:** Proxy maintains one active trace, reset via /traces/reset
**Alternatives:** Trace ID in headers (client complexity), auto-new per request (loses context)
**Consequences:** Simple implementation, but only one agent at a time per proxy instance

### `src/agentlens/__init__.py` (UPDATE)
**Purpose:** Clean up public API
**Changes:**
- Add docstring with usage example
- Export EvaluationSuite from engine
- Export print_report, generate_html_report from report
- Add `__version__ = "0.1.0"`
**Final exports:**
```python
__all__ = [
    # Version
    "__version__",
    # Models
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
    # Capture
    "Tracer",
    # Evaluation
    "EvaluationSuite",
    "Evaluator",
    # Reports
    "print_report",
    "generate_html_report",
]
```

### `tests/test_e2e.py`
**Purpose:** End-to-end test of full pipeline
**Tests:**
- `test_e2e_fixture_demo_all_scenarios` — Load all fixtures, evaluate, verify no crashes
- `test_e2e_cli_demo_command` — Run `agentlens demo` via subprocess, verify exit 0
- `test_e2e_cli_evaluate_command` — Run `agentlens evaluate` on fixture, verify output
- `test_e2e_html_report_valid_html` — Generate HTML, verify it's parseable
- `test_e2e_proxy_mock_mode` — Start server, make request, verify trace captured
**Constraints:**
- Use `subprocess.run` for CLI tests with timeout
- Use `TestClient` for server tests
- Keep tests fast (< 5s each)

## Verification

After implementation:
1. `uv run agentlens demo` — Full demo works
2. `uv run agentlens demo --html -o report.html && open report.html` — HTML looks good
3. `uv run pytest` — All tests pass including e2e
4. `uv run ruff check .` — No lint errors
5. `uv run pyright .` — Type check passes
6. README renders correctly on GitHub
7. ARCHITECTURE.md is comprehensive

## Final Checklist

- [ ] All 12 evaluators implemented and tested
- [ ] Proxy server works in mock and proxy modes
- [ ] CLI commands work: demo, evaluate, serve
- [ ] Terminal report is readable and color-coded
- [ ] HTML report is self-contained and looks professional
- [ ] README has quick start that works in < 1 minute
- [ ] ARCHITECTURE.md documents all layers
- [ ] decisions.md has 4 ADRs
- [ ] All tests pass
- [ ] No lint errors, no type errors
- [ ] `uv run agentlens demo` is impressive
