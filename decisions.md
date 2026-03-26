# Architecture Decision Records

## 2026-03-26 — OpenAI-Compatible Proxy Over SDK Wrappers

**Status:** accepted

**Context:** AgentLens needs to capture traces from any LLM-backed agent framework without requiring code changes in the agent itself. The capture mechanism must work regardless of which Python LLM library the agent uses (openai, anthropic, litellm, langchain, etc.).

**Decision:** Build a local FastAPI proxy server that speaks the OpenAI Chat Completions API. Agents point their `OPENAI_API_BASE` (or equivalent) at `http://localhost:8650/v1`. The proxy intercepts every request, records the spans, and either returns a canned mock response or forwards to a real upstream provider.

**Alternatives considered:**
- *LiteLLM as the proxy layer* — LiteLLM was compromised in a supply-chain attack in March 2026, making it a security risk as a dependency.
- *Per-SDK wrappers* — Would require one wrapper per provider (openai, anthropic, cohere, …), explosion of maintenance surface.
- *OpenTelemetry instrumentation* — Too heavy for a focused evaluation tool; requires running a collector and defining custom span schemas on top of OTEL primitives.

**Consequences:** Any agent framework that supports `OPENAI_API_BASE` works without code changes. The tradeoff is that the proxy server must be running during agent execution. Only one active trace at a time (see ADR below).

---

## 2026-03-26 — Deterministic Evaluators Over LLM-as-Judge

**Status:** accepted

**Context:** Evaluation quality depends on reproducibility. LLM-based judges introduce non-determinism: the same trace can receive different scores on different runs, making CI comparisons unreliable. They also add latency and cost to every evaluation run.

**Decision:** All 12 evaluators in AgentLens are rule-based and deterministic. They inspect the trace structure (span types, tool names, durations, token counts, output text) using explicit conditions — no LLM calls during evaluation.

**Alternatives considered:**
- *LLM-as-judge* — Non-deterministic, adds latency, costs money, and is unsuitable for CI/CD gating.
- *Hybrid (deterministic + LLM for semantic checks)* — Would be useful for semantic similarity scoring, but adds complexity and a required API key. Not implemented in v0.1; could be added as an optional evaluator group.

**Consequences:** Evaluations run in milliseconds, cost nothing, and produce identical results across runs — making them CI-safe. The limitation is that purely semantic quality (e.g., "was the answer factually correct?") requires a human review or a separate semantic layer not provided by AgentLens.

---

## 2026-03-26 — Pre-Recorded Fixtures as Default Demo

**Status:** accepted

**Context:** The demo command must work instantly for new users without any API keys, environment setup, or running services. It also needs to be deterministic so the output is predictable in documentation and screencasts.

**Decision:** Ship three pre-recorded trace JSON files (`happy_path.json`, `loop_scenario.json`, `risk_scenario.json`) as fixtures. `uv run agentlens demo` loads these fixtures directly. A `--live` flag is reserved for future real execution but is gated behind explicit opt-in.

**Alternatives considered:**
- *Always live* — Requires an API key and a real LLM provider; breaks the zero-friction goal.
- *Mock-only with no fixtures* — Could generate synthetic traces at runtime, but the output would be less realistic and harder to document.

**Consequences:** Zero-friction demo — clone and run in seconds. The fixture traces are realistic (sourced from the mock proxy replay) and demonstrate all three evaluation scenarios clearly. The downside is that fixtures can go stale if the `Trace` model schema changes; they must be regenerated on breaking schema changes.

---

## 2026-03-26 — Single Trace Per Proxy Session

**Status:** accepted

**Context:** The proxy server must associate incoming spans with a trace. In a multi-agent or parallel-agent setup this requires a per-request correlation mechanism (e.g., a `X-Trace-Id` header). For v0.1, simplicity is the priority.

**Decision:** The proxy maintains one active `current_spans` list. A `POST /traces/reset` call finalizes the current list into a `Trace` and clears the buffer for the next agent run. Spans accumulate until explicitly reset.

**Alternatives considered:**
- *Trace ID headers* — Would support concurrent agents, but requires the agent to inject a custom header, which most frameworks don't do by default.
- *Auto-new trace per request* — Creates a new trace on every LLM call, making multi-turn conversations impossible to track as a single trajectory.

**Consequences:** Simple to reason about and implement. Works correctly for single-agent, sequential execution — the primary use case. The limitation is that concurrent agents sharing the same proxy instance will have their spans interleaved. For concurrent use, run separate proxy instances on different ports.
