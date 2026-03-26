# AgentLens — Implementation Plan Overview

**Date:** 2026-03-26
**Spec reference:** `docs/IMPLEMENTATION_PLAN.md`
**Project type:** Python 3.13 + FastAPI + uv
**Subagent type:** `python-fastapi` (Phases 1-4), `general-purpose` (Phase 5)

---

## Phase Summary

| Phase | Title | New Files | Tests | Agent | Depends On |
|-------|-------|-----------|-------|-------|-----------|
| 1 | Scaffold + Core Models | 12 | 4 test files | `python-fastapi` | — |
| 2 | Observability Server | 5 | 1 test file | `python-fastapi` | Phase 1 (models) |
| 3 | Evaluators | 7 | 5 test files | `python-fastapi` | Phase 1-2 |
| 4 | Demo + Reporting | 10 | 2 test files | `python-fastapi` | Phases 1-3 |
| 5 | Polish | 5 | 1 test file | `general-purpose` | Phases 1-4 |

## Implementation Order

```
Phase 1 ──→ Phase 2 ──→ Phase 3 ──→ Phase 4 ──→ Phase 5
(models)    (server)    (evals)     (demo+cli)   (docs)
```

All phases are sequential. Each builds on the previous.

## Cross-Phase Dependencies

| Producer (Phase) | Artifact | Consumer (Phase) |
|-------------------|----------|-------------------|
| 1 | `Trace`, `Span`, `SpanType`, `SpanStatus`, `TokenUsage` | 2, 3, 4 |
| 1 | `EvalResult`, `EvalSummary`, `EvalLevel`, `EvalSeverity` | 3, 4 |
| 1 | `TaskExpectation` | 3, 4 |
| 1 | `Tracer` context manager | 4 |
| 2 | Proxy server (mock + proxy modes) | 4 (live demo) |
| 2 | `CannedResponseRegistry` | 4 (scenarios) |
| 3 | `Evaluator` Protocol + all 12 evaluators | 4 |
| 3 | `EvaluationSuite` engine | 4 |
| 4 | Fixture traces, CLI, reports | 5 (docs, e2e test) |

## Detailed Plans

- `IMPLEMENTATION_PLAN_PHASE_1.md` — Scaffold + Core Models
- `IMPLEMENTATION_PLAN_PHASE_2.md` — Observability Server
- `IMPLEMENTATION_PLAN_PHASE_3.md` — Evaluators
- `IMPLEMENTATION_PLAN_PHASE_4.md` — Demo + Reporting
- `IMPLEMENTATION_PLAN_PHASE_5.md` — Polish

## Verification (after all phases)

```bash
uv sync                                    # deps install cleanly
uv run pytest                              # all tests pass
uv run agentlens demo                      # 3 scenarios, terminal output
uv run agentlens demo --scenario happy     # single scenario
uv run agentlens demo --html -o report.html # HTML report
uv run agentlens evaluate demo/fixtures/risk_scenario.json  # evaluate trace file
uv run agentlens serve --mode mock         # proxy server starts, curl /health
uv run ruff check src/                     # no lint errors
uv run pyright src/                        # no type errors
```
