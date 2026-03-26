# AgentLens — Mailbox Adapter Implementation Plan

**Date:** 2026-03-26
**Spec reference:** `docs/ADAPTER_PLAN.md`
**Project type:** Python 3.13 + FastAPI + uv

---

## Phase Summary

| Phase | Title | New Files | Modified Files | Tests | Agent | Depends On |
|-------|-------|-----------|----------------|-------|-------|-----------|
| A | Refactor — Extract Trace Collector | 2 | 2 | 1 test file | `python-fastapi` | — |
| B | Mailbox Adapter | 2 | 2 | 1 test file | `python-fastapi` | Phase A |
| C | Integration Example | 3 | 0 | 0 | `general-purpose` | Phase B |

## Implementation Order

```
Phase A ──→ Phase B ──→ Phase C
(refactor)   (mailbox)   (example)
```

## Cross-Phase Dependencies

| Producer (Phase) | Artifact | Consumer (Phase) |
|-------------------|----------|-------------------|
| A | `TraceCollector` class | B (mailbox uses it to emit spans) |
| A | Refactored `proxy.py` using `TraceCollector` | B (adds mailbox mode branch) |
| B | Mailbox endpoints + `--mode mailbox` | C (example scripts use them) |

## Detailed Plans

- `IMPLEMENTATION_PLAN_PHASE_A.md` — Refactor: Extract Trace Collector
- `IMPLEMENTATION_PLAN_PHASE_B.md` — Mailbox Adapter
- `IMPLEMENTATION_PLAN_PHASE_C.md` — Integration Example

## Verification (after all phases)

```bash
uv run pytest                              # all tests pass (existing + new)
uv run agentlens serve --mode mock         # existing mock still works
uv run agentlens serve --mode mailbox      # new mailbox mode starts
uv run ruff check src/                     # no lint errors
uv run pyright src/                        # no type errors
```
