# AgentLens — P1 Bug Fixes Implementation Plan

**Date:** 2026-03-26
**Spec reference:** `TODOS.md` (Priority 1 section)
**Project type:** Python 3.13 + FastAPI + uv

---

## Phase Summary

| Phase | Title | New Files | Modified Files | Tests | Agent | Depends On |
|-------|-------|-----------|----------------|-------|-------|-----------|
| P1 | Fix span timestamps, token usage, agent identity | 0 | 6 | 2 modified | `python-fastapi` | — |

All 3 P1 fixes are tightly coupled (they all modify `collector.py` and `proxy.py`), so they ship as one phase.

## Detailed Plan

- `IMPLEMENTATION_PLAN_PHASE_P1.md` — All 3 bug fixes

## Verification

```bash
uv run pytest tests/ -v
uv run pyright src/
uv run ruff check src/ tests/
uv run agentlens demo --verbose     # spans should show real durations, token counts, agent names
```
