# AgentLens — P2 Features Implementation Plan

**Date:** 2026-03-26
**Spec reference:** `TODOS.md` (Priority 2 section)
**Project type:** Python 3.13 + FastAPI + uv

---

## Phase Summary

| Phase | Title | New Files | Modified Files | Tests | Agent | Depends On |
|-------|-------|-----------|----------------|-------|-------|-----------|
| P2.1 | RAG Span Types + Evaluators | 1 new evaluator file | 3 modified | 1 test file | `python-fastapi` | — |
| P2.2 | Session/Conversation Grouping | 0 | 4 modified | 1 test file modified | `python-fastapi` | — |
| P2.3 | OTel-Compatible Export | 2 new | 1 modified | 1 test file | `python-fastapi` | — |
| P2.4 | Benchmark Suite | 2 new + 1 fixture | 1 modified | 1 test file | `python-fastapi` | — |

## Implementation Order

```
P2.1 ──┐
P2.2 ──┼── all independent, can run in any order
P2.3 ──┤
P2.4 ──┘
```

No cross-dependencies. Each phase is self-contained.

## Detailed Plans

- `IMPLEMENTATION_PLAN_PHASE_P2_1.md` — RAG Span Types + Evaluators
- `IMPLEMENTATION_PLAN_PHASE_P2_2.md` — Session Grouping
- `IMPLEMENTATION_PLAN_PHASE_P2_3.md` — OTel Export
- `IMPLEMENTATION_PLAN_PHASE_P2_4.md` — Benchmark Suite

## Verification (after all phases)

```bash
uv run pytest
uv run pyright src/
uv run ruff check src/ tests/
uv run agentlens demo --verbose
uv run agentlens export-otel traces/some-trace.json
uv run agentlens benchmark run benchmarks/default.json
```
