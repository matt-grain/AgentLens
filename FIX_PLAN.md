# Fix Plan — AgentLens

**Date:** 2026-03-26
**Based on:** REVIEW.md dated 2026-03-26
**Project type:** Python 3.13 / FastAPI

## Summary

| Phase | Fix Units | Files Affected | Estimated Effort |
|-------|-----------|---------------|-----------------|
| Phase 0 — Micro-fixes | 5 | 14 | Low (30 min) |
| Phase 1 — Structural | 4 | 12 | Medium (1-2 hours) |
| Phase 2 — Architectural | 1 | 3 | Medium (1 hour) |
| **Total** | **10** | **~25** | |

**Agents required:** `python-fastapi`

---

## Phase 0 — Micro-fixes

### Fix Unit 0.1: Add `@unique` to all StrEnums
- **Category:** State & Enums
- **Agent:** `python-fastapi`
- **Files:**
  - `src/agentlens/models/trace.py`
  - `src/agentlens/models/evaluation.py`
- **Violation pattern:** `class.*StrEnum` without preceding `@unique`
- **Expected after fix:** All 4 StrEnum classes decorated with `@unique`
- **HOW TO FIX:**
  1. In `trace.py`: add `from enum import StrEnum, unique` (replace existing `from enum import StrEnum`)
  2. Add `@unique` decorator above `class SpanType(StrEnum):` and `class SpanStatus(StrEnum):`
  3. In `evaluation.py`: same — add `unique` to import, add `@unique` above both enum classes

### Fix Unit 0.2: Remove dead code + add missing `__future__` imports
- **Category:** Typing & Style
- **Agent:** `python-fastapi`
- **Files:**
  - `src/agentlens/capture/tracer.py` — remove `if TYPE_CHECKING: pass` block (lines 9-10)
  - `src/agentlens/evaluators/__init__.py` — remove `if TYPE_CHECKING: pass` block (lines 11-12)
  - `src/agentlens/__init__.py` — add `from __future__ import annotations` as first import
  - `src/agentlens/models/__init__.py` — add `from __future__ import annotations` as first import
- **HOW TO FIX:**
  1. In `tracer.py`: delete lines 9-10 (`if TYPE_CHECKING:\n    pass`), remove `TYPE_CHECKING` from the typing import if no longer used
  2. In `evaluators/__init__.py`: delete lines 11-12, remove unused `TYPE_CHECKING` import
  3. In both `__init__.py` files: add `from __future__ import annotations` as the very first line after the module docstring

### Fix Unit 0.3: Replace bare `assert` with explicit guards
- **Category:** Architecture
- **Agent:** `python-fastapi`
- **Files:**
  - `src/agentlens/server/proxy.py` (lines 109, 160)
  - `src/agentlens/capture/tracer.py` (line 137)
- **Violation pattern:** `assert mailbox is not None` / `assert self._started_at is not None`
- **HOW TO FIX:**
  1. In `proxy.py` line 109: replace `assert mailbox is not None` with `if mailbox is None: raise RuntimeError("Mailbox not initialized in mailbox mode")`
  2. In `proxy.py` line 160: same replacement
  3. In `tracer.py` line 137: replace `assert self._started_at is not None` with `if self._started_at is None: raise RuntimeError("Tracer was not entered as context manager")`

### Fix Unit 0.4: Add justification to all `# type: ignore` and `# noqa` suppressions
- **Category:** Typing & Style
- **Agent:** `python-fastapi`
- **Files:**
  - `src/agentlens/server/proxy.py` (11 occurrences of `# type: ignore[reportUnusedFunction]`)
  - `src/agentlens/cli.py` (1x `# type: ignore[import-untyped]`, 1x `# noqa: S104`)
  - `src/agentlens/evaluators/behavior.py` (1x `# noqa: S324`)
- **HOW TO FIX:**
  1. In `proxy.py`: add a block comment ONCE before the first route handler inside `create_app()`:
     ```python
     # Pyright reports nested FastAPI route handlers as unused functions.
     # They are registered by @app.get/@app.post decorators at definition time.
     ```
     Then change all 11 occurrences from `# type: ignore[reportUnusedFunction]` to `# type: ignore[reportUnusedFunction]  # FastAPI route handler`
  2. In `cli.py` line 45: change to `# type: ignore[import-untyped]  # demo/ is an unpackaged script directory`
  3. In `cli.py` line 128: change to `# noqa: S104  # intentional: dev proxy binds all interfaces`
  4. In `behavior.py` line 124: change to `# noqa: S324  # MD5 for non-cryptographic span fingerprinting`

### Fix Unit 0.5: Add `@pytest.mark.e2e` to subprocess tests
- **Category:** Testing
- **Agent:** `python-fastapi`
- **Files:**
  - `tests/test_e2e.py`
  - `pyproject.toml` (add marker registration)
- **HOW TO FIX:**
  1. In `pyproject.toml` under `[tool.pytest.ini_options]`, add: `markers = ["e2e: end-to-end tests requiring subprocess"]`
  2. In `test_e2e.py`: add `import pytest` if not present
  3. Add `@pytest.mark.e2e` decorator above `test_e2e_cli_demo_command` and `test_e2e_cli_evaluate_command` (the two subprocess tests)
  4. The other 3 tests in the file (fixture pipeline, HTML report, proxy mock) do NOT use subprocess — leave them unmarked

---

## Phase 1 — Structural

### Fix Unit 1.1: Define `ServerMode`, `FinishReason`, `MessageRole` StrEnums
- **Category:** State & Enums (Critical)
- **Agent:** `python-fastapi`
- **Dependencies:** Fix Unit 0.1 must be done (enum import pattern established)
- **Files:**
  - `src/agentlens/server/models.py` — add 3 new StrEnums, update `Choice.finish_reason` type
  - `src/agentlens/server/proxy.py` — replace all `mode == "mock"` with `ServerMode.MOCK`, replace `Literal` usage, replace finish_reason ternaries
  - `src/agentlens/server/collector.py` — replace `m.role == "user"` with `MessageRole.USER`
  - `src/agentlens/cli.py` — change `mode` param type to `ServerMode`, remove ternary remapping
- **HOW TO FIX:**
  1. In `server/models.py`, add at the top (after imports):
     ```python
     from enum import StrEnum, unique

     @unique
     class ServerMode(StrEnum):
         MOCK = "mock"
         PROXY = "proxy"
         MAILBOX = "mailbox"

     @unique
     class FinishReason(StrEnum):
         STOP = "stop"
         TOOL_CALLS = "tool_calls"

     @unique
     class MessageRole(StrEnum):
         SYSTEM = "system"
         USER = "user"
         ASSISTANT = "assistant"
         TOOL = "tool"
     ```
  2. Update `ChatMessage.role` type from `Literal["system", "user", "assistant", "tool"]` to `MessageRole`
  3. Update `Choice.finish_reason` type from `Literal["stop", "tool_calls"]` to `FinishReason`
  4. In `proxy.py`: import `ServerMode`, `FinishReason` from `server.models`. Change `create_app(mode: Literal["mock", "proxy", "mailbox"]` to `mode: ServerMode = ServerMode.MOCK`. Replace all `mode == "mock"` with `mode == ServerMode.MOCK` etc. Replace all 3 `finish_reason: Literal[...]` ternaries with `FinishReason.TOOL_CALLS if tool_calls else FinishReason.STOP`
  5. In `collector.py`: import `MessageRole` from `server.models`. Replace `m.role == "user"` with `m.role == MessageRole.USER`
  6. In `cli.py`: import `ServerMode` from `agentlens.server.models`. Change `mode` param annotation to `ServerMode`. Remove the ternary remapping lines 116-118 — just pass `mode` directly to `create_app(mode=mode, ...)`
  7. Update `server/__init__.py` to export `ServerMode` if needed

### Fix Unit 1.2: Create shared test factories
- **Category:** Testing (Critical)
- **Agent:** `python-fastapi`
- **Files:**
  - `tests/test_evaluators/conftest.py` (CREATE)
  - `tests/test_evaluators/test_behavior.py` (remove local `_span`/`_trace`, use shared)
  - `tests/test_evaluators/test_business.py` (remove local `_make_trace`, use shared)
  - `tests/test_evaluators/test_risk.py` (remove local `_span`/`_trace`, use shared)
  - `tests/test_evaluators/test_operational.py` (remove local `_span`/`_trace`, use shared)
  - `tests/test_engine.py` (remove local `_make_trace`, use shared from conftest)
- **HOW TO FIX:**
  1. Create `tests/test_evaluators/conftest.py` with shared helpers:
     ```python
     def make_span(sid, span_type, name, inp=None, output=None,
                   status=SpanStatus.SUCCESS, offset_ms=0, duration_ms=100,
                   parent_id=None, token_usage=None) -> Span: ...
     def make_trace(spans, task="test task", final_output=None, total_duration_ms=None) -> Trace: ...
     ```
  2. Read each of the 5 files' existing `_span`/`_trace`/`_make_trace` helpers to understand their signatures
  3. The shared `make_span` should be a superset of all existing signatures (union of all params)
  4. In each test file: remove the local helper, import from conftest (pytest auto-discovers it)
  5. Update call sites — adjust param names if they differ slightly between files
  6. Run `uv run pytest tests/test_evaluators/ tests/test_engine.py -v` to verify

### Fix Unit 1.3: Add version caps to pyproject.toml
- **Category:** Documentation & Debt
- **Agent:** `python-fastapi`
- **Files:**
  - `pyproject.toml`
- **HOW TO FIX:**
  1. Update runtime dependencies to add upper bounds:
     ```
     "pydantic>=2.0,<3",
     "rich>=13.0.0,<14",
     "typer[all]>=0.9.0,<1",
     "jinja2>=3.1.0,<4",
     "fastapi>=0.115.0,<1",
     "uvicorn[standard]>=0.32.0,<1",
     "httpx>=0.27.0,<1",
     ```
  2. Run `uv lock` to regenerate lockfile

### Fix Unit 1.4: Add missing test files for canned.py and server models
- **Category:** Testing
- **Agent:** `python-fastapi`
- **Files:**
  - `tests/test_canned.py` (CREATE)
  - `tests/test_server_models.py` (CREATE)
- **HOW TO FIX:**
  1. Create `tests/test_canned.py` with tests:
     - `test_registry_next_response_cycles` — register 2 responses, call next_response 3 times, verify cycling
     - `test_registry_reset_resets_index` — advance index, reset, verify starts from 0
     - `test_registry_unknown_scenario_raises` — next_response with bad name raises KeyError
     - `test_builtin_scenarios_registered` — verify "happy_path", "loop", "risk", "pharma_pipeline" all exist
  2. Create `tests/test_server_models.py` with tests:
     - `test_chat_message_user_role` — create ChatMessage with role="user", verify
     - `test_chat_completion_request_defaults` — verify temperature=1.0, max_tokens=None defaults
     - `test_chat_completion_response_structure` — create full response, verify model_dump produces valid JSON

---

## Phase 2 — Architectural

### Fix Unit 2.1: Split proxy.py (284 → ~160 lines)
- **Category:** Architecture
- **Agent:** `python-fastapi`
- **Dependencies:** Fix Units 1.1 (ServerMode enum) must be done first
- **Files:**
  - `src/agentlens/server/proxy.py` (MODIFY — keep core app factory + main endpoints)
  - `src/agentlens/server/response.py` (CREATE — unified response builder)
  - `src/agentlens/server/upstream.py` (CREATE — `_proxy_request` function)
- **SPLIT PLAN:**
  - `response.py` (~30 lines): Move and merge `_canned_to_response` + `_build_openai_response` into a single `build_openai_response(content, tool_calls, usage, model) -> ChatCompletionResponse`
  - `upstream.py` (~45 lines): Move `_proxy_request` function as-is
  - `proxy.py` keeps: `create_app`, all route handlers, `_register_mailbox_endpoints`
  - Expected proxy.py size after split: ~160 lines
- **HOW TO FIX:**
  1. Create `server/response.py` with a single `build_openai_response(content, tool_calls, usage, model)` that replaces both existing builders. Use `FinishReason` enum.
  2. Create `server/upstream.py` with `async def proxy_request(request, proxy_target) -> tuple[...]` — move from proxy.py as-is, using the new `build_openai_response`
  3. In `proxy.py`: import `build_openai_response` from `response`, import `proxy_request` from `upstream`. Delete the old local functions. Update call sites.
  4. Run full test suite — behavior must be identical

---

## Deferred Items (not planned)

| Item | Reason |
|------|--------|
| Move enums to dedicated `enums/` directory | Acceptable at current project size; enums co-located with models is clear enough |
| Decouple `collector.py` from `ChatMessage` | Low impact; the coupling is within the server/ package |
| Refactor `CannedRegistry` singleton | Works fine for current use; only matters if tests need isolation |
| `ServerConfig` dataclass for `create_app` params | 6 params is at the limit but not over; revisit if more params added |
| Add `--host` option to serve command | Enhancement, not a fix |
| AAA markers in 5 test files | Cosmetic; tests are clear without them at current size |
| Move `test_client` fixture to shared conftest | Low impact |
| Engine test name improvements | Cosmetic |

## Execution Notes

- Run `/fix-review` to execute this plan. It will read this file and dispatch subagents in phase order.
- Phase 0 can be done as a single subagent dispatch (all mechanical).
- Phase 1 units 1.1 and 1.2 are independent — can run in parallel.
- Phase 2 depends on Phase 1 unit 1.1 (needs `ServerMode` enum).
- After all fixes: `uv run pytest && uv run pyright src/ && uv run ruff check src/ tests/`
