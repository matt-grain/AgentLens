# Architecture Review — AgentLens

**Date:** 2026-03-26
**Project type:** Python 3.13 / FastAPI

## Executive Summary

| Category | Conformance | Critical | Warnings | Info |
|----------|------------|----------|----------|------|
| Architecture & SoC | High | 0 | 4 | 4 |
| Typing & Style | High | 0 | 2 | 8 |
| State & Enums | Medium | 3 | 4 | 2 |
| Testing | Medium | 2 | 4 | 3 |
| Documentation & Debt | High | 0 | 2 | 8 |

### Top Findings

1. **`ServerMode` should be a StrEnum** — `mode` is typed as `str` in CLI, `Literal` in proxy, with raw string comparisons throughout. Defines a fixed set but doesn't use an enum. (State & Enums)
2. **`proxy.py` is 284 lines** — contains response builders, route closures, mailbox registration, and upstream proxying. Should be split. (Architecture + Docs)
3. **No shared test factories** — 5 evaluator test files independently define identical `_span()`/`_trace()` helpers instead of sharing via conftest. (Testing)
4. **Floating dependency versions** — all `>=` without upper bounds in pyproject.toml. (Docs & Debt)
5. **`Any` used without justification comments** — ~25 occurrences across server/ and capture/ modules. (Typing)

## Detailed Findings

### 1. Architecture & Separation of Concerns

| Severity | Finding | File(s) | Rule Violated | Recommendation |
|----------|---------|---------|---------------|----------------|
| 🟡 | `proxy.py` is 284 lines with 3 distinct responsibilities | `server/proxy.py` | Module size >200; SRP | Extract `_proxy_request` to `server/upstream.py`, mailbox routes to `server/mailbox_routes.py`, unify duplicate response builders |
| 🟡 | `collector.py` imports `ChatMessage` from server HTTP DTOs | `server/collector.py:11` | Cross-layer coupling | Accept `list[dict[str, Any]]` or define a minimal Protocol |
| 🟡 | `REGISTRY` is a module-level mutable singleton mutated at import time | `server/canned.py` | Module-level mutable state | Move to a factory function, inject into `create_app` |
| 🟡 | Two near-identical response builder helpers | `server/proxy.py:27-73` | DRY | Merge into single `_build_response()` |
| 🔵 | Empty `if TYPE_CHECKING: pass` blocks | `evaluators/__init__.py`, `capture/tracer.py` | Dead code | Remove |
| 🔵 | `cli.py` uses `sys.path.insert` hack for demo imports | `cli.py:17-21` | Path surgery | Add existence check or install demo as extras |
| 🔵 | `server/models.py` naming ambiguity with `models/` | `server/models.py` | Discoverability | Consider renaming to `server/openai_schemas.py` |
| 🔵 | Bare `assert` for runtime invariants in server code | `proxy.py:109,160`, `tracer.py:137` | Assertions stripped with -O | Replace with explicit guards |

**Clean areas:** models/ is pure data, evaluators/ have zero cross-layer imports, engine.py imports only models + evaluators, report/ is pure rendering, no circular imports detected, no catch-all utils files.

### 2. Typing & Style

| Severity | Finding | File(s) | Rule Violated | Recommendation |
|----------|---------|---------|---------------|----------------|
| 🟡 | `Any` used ~25 times without justification comments | `server/proxy.py`, `server/collector.py`, `capture/tracer.py`, `server/mailbox.py` | Any requires justification | Add inline comments; consider TypedDicts for known shapes |
| 🟡 | 13x `# type: ignore[reportUnusedFunction]` without explanation | `server/proxy.py` | Suppressions must be justified | Add one block comment explaining FastAPI closure pattern |
| 🔵 | `from __future__ import annotations` missing in 2 init files | `__init__.py`, `models/__init__.py` | Consistency | Add to both |
| 🔵 | `_build_llm_span` and `create_app` have 6 parameters each | `collector.py`, `proxy.py` | Max 5 params | Group into config dataclass |
| 🔵 | `# noqa: S104`, `# noqa: S324`, `# type: ignore[import-untyped]` without context | `cli.py`, `behavior.py` | Suppressions must explain why | Add brief justification text |

**Clean areas:** All functions have return types, no `== None`, no bare except, no `.format()`, no wildcard imports, consistent naming conventions.

### 3. State Management & Enums

| Severity | Finding | File(s) | Rule Violated | Recommendation |
|----------|---------|---------|---------------|----------------|
| 🔴 | `mode` uses `Literal` + raw string comparisons in 5+ locations | `proxy.py`, `cli.py` | Enums mandatory for fixed sets | Define `ServerMode(StrEnum)` |
| 🔴 | `finish_reason` computed as `Literal["stop", "tool_calls"]` in 3 separate locations | `proxy.py:28,57,267` | DRY + enums for fixed sets | Define `FinishReason(StrEnum)` + single helper |
| 🔴 | CLI `mode` param typed as bare `str` — invalid input silently falls to "mock" | `cli.py:99,116-118` | Fail fast; enums for CLI params | `ServerMode(StrEnum)` makes typer validate automatically |
| 🟡 | `m.role == "user"` raw string comparisons for message roles | `collector.py`, `proxy.py` | Enums for fixed sets | Define `MessageRole(StrEnum)` |
| 🟡 | 4 existing StrEnums missing `@unique` decorator | `models/trace.py`, `models/evaluation.py` | Enum correctness | Add `@unique` to all 4 |
| 🟡 | Enums mixed in model files instead of dedicated `enums/` directory | `models/trace.py`, `models/evaluation.py` | Architecture layout | Not urgent — current co-location with models is acceptable for this project size |
| 🟡 | `MailboxEntry` lifecycle tracked implicitly via 3 separate dicts | `server/mailbox.py` | FSM for stateful entities | Add `MailboxEntryStatus(StrEnum)` field |

**Clean areas:** SpanType, SpanStatus, EvalLevel, EvalSeverity are proper StrEnums. Trace/EvalSummary are correctly modeled as immutable value objects, not stateful entities.

### 4. Testing Quality

| Severity | Finding | File(s) | Rule Violated | Recommendation |
|----------|---------|---------|---------------|----------------|
| 🔴 | No shared test factories — 5 files independently define identical `_span()`/`_trace()` helpers | `test_evaluators/*.py`, `test_engine.py` | Use factories, not inline data | Create shared helpers in `tests/test_evaluators/conftest.py` |
| 🔴 | 5 test files lack AAA section markers | `test_cli.py`, `test_report.py`, `test_models.py`, `test_tracer.py`, `test_server.py` | AAA pattern with clear sections | Add `# Arrange`, `# Act`, `# Assert` comments |
| 🟡 | `server/canned.py` and `server/models.py` have no dedicated test files | — | Every module needs tests | Add `test_canned.py` and `test_server_models.py` |
| 🟡 | `test_server.py` defines local `test_client` fixture instead of sharing via conftest | `test_server.py:11-14` | Shared fixtures in conftest | Move to `tests/conftest.py` |
| 🟡 | Engine test names lack expected outcome segment | `test_engine.py` | `test_<action>_<scenario>_<expected>` | Add outcome to names |
| 🟡 | E2E subprocess tests have no `@pytest.mark.e2e` skip guard | `test_e2e.py` | Test isolation | Add marker for CI |

**Clean areas:** 100% source module coverage (all 10 modules have test files except canned.py and models.py), 123 tests passing, e2e tests exist, conftest.py has 4 reusable fixtures.

### 5. Documentation & Cognitive Debt

| Severity | Finding | File(s) | Rule Violated | Recommendation |
|----------|---------|---------|---------------|----------------|
| 🟡 | All 10 runtime dependencies use `>=` without upper bounds | `pyproject.toml` | Floating versions | Add caps: `pydantic>=2.0,<3`, `fastapi>=0.115.0,<1`, etc. |
| 🟡 | `proxy.py` at 284 lines (only file over limit) | `server/proxy.py` | Module size >200 | Split (see Architecture section) |

**Clean areas:** ARCHITECTURE.md complete with all 6 required sections, decisions.md has 4 ADRs, README.md is comprehensive, uv.lock committed, zero TODOs/FIXMEs in source, no f-string SQL, no CORS wildcards, no hardcoded secrets, no time.sleep in async.

## Migration Plan

### Phase 0 — Quick Wins (mechanical, low risk)
- [ ] Add `@unique` to all 4 StrEnums (4 one-line changes)
- [ ] Remove empty `if TYPE_CHECKING: pass` blocks (2 files)
- [ ] Add `from __future__ import annotations` to 2 init files
- [ ] Add justification comments to all `# type: ignore` and `# noqa` suppressions
- [ ] Add justification comments to `Any` usages
- [ ] Replace bare `assert` with explicit guards in `proxy.py` and `tracer.py`
- [ ] Add `@pytest.mark.e2e` to subprocess tests in `test_e2e.py`

### Phase 1 — Structural Improvements (medium effort)
- [ ] Define `ServerMode(StrEnum)` — eliminates raw string mode comparisons in proxy.py + cli.py
- [ ] Define `FinishReason(StrEnum)` — removes triplicated ternary
- [ ] Define `MessageRole(StrEnum)` — replaces Literal on ChatMessage.role
- [ ] Create shared test factories in `tests/test_evaluators/conftest.py`
- [ ] Add AAA markers to 5 test files missing them
- [ ] Add `test_canned.py` and `test_server_models.py`
- [ ] Add upper-bound version caps to pyproject.toml dependencies
- [ ] Move `test_client` fixture to shared conftest

### Phase 2 — Architectural Changes (higher effort)
- [ ] Split `proxy.py` — extract upstream client, mailbox routes, unify response builders
- [ ] Decouple `collector.py` from `ChatMessage` — accept raw dicts or Protocol
- [ ] Refactor `CannedRegistry` from module-level singleton to injected factory

### Phase 3 — Ongoing Discipline
- [ ] Monitor `behavior.py` (199 lines) — split if a 5th evaluator is added
- [ ] Consider `ServerConfig` dataclass to reduce `create_app` parameter count
- [ ] Add `--host` option to serve command for network restriction
