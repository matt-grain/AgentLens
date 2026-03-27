# AgentLens — Future Improvements

## Evidence Detection Improvements

### Regex-Based Evidence Tracking
Currently `HallucinationFlag` checks if ANY tool call preceded a numeric claim. A smarter approach would trace specific numbers back through the span chain:
- Extract numbers from tool results (e.g., search returns "$3.05 trillion")
- Extract numbers from LLM output (e.g., agent says "$3.05 trillion")
- Match them — if the output number appears in a prior tool result, it's grounded
- Flag only numbers that have NO match in any prior tool/message content
- This would eliminate false positives from valid aggregation (e.g., `4.43 - 3.05 = 1.38`)

### Optional LLM-as-Judge Evaluator

**Architecture decision:** The judge MUST be a native AgentLens evaluator, NOT a CrewAI agent or any external framework agent. Reason: if the judge were an agent going through the proxy, its own LLM calls would be captured as spans — polluting the trace being evaluated. Circular observation.

The separation of concerns:
```
Proxy (observes)  ≠  Evaluation (judges)

Proxy captures agent behavior → Trace JSON
Evaluators analyze the trace → EvalResults

The judge is an evaluator, not an agent.
It calls the LLM directly (httpx → provider API), bypassing the proxy entirely.
```

Design:
```python
class LLMJudgeEvaluator:
    """LLM-based evaluator for nuanced trace analysis.

    Calls the LLM directly — NOT through the AgentLens proxy.
    This is an evaluator (judges traces), not an agent (produces traces).
    """
    name = "llm_judge"
    level = EvalLevel.RISK  # or configurable per-call

    def __init__(
        self,
        model: str = "claude-sonnet-4-6",
        base_url: str = "https://api.anthropic.com",
        api_key: str | None = None,  # from env if None
    ):
        self._client = httpx.Client(base_url=base_url, ...)

    def evaluate(self, trace: Trace, expected: TaskExpectation | None = None) -> list[EvalResult]:
        # Serialize trace + expectations into a structured prompt
        # Ask the LLM: "Analyze this agent trajectory for:
        #   1. Are numeric claims grounded in tool results?
        #   2. Are there subtle policy violations (paraphrased)?
        #   3. Is the reasoning coherent across steps?
        #   4. Overall quality assessment"
        # Parse structured JSON response into EvalResult(s)
        ...
```

Usage — opt-in, alongside deterministic evaluators:
```python
suite = EvaluationSuite()  # 12 deterministic evaluators by default
suite.add_evaluator(LLMJudgeEvaluator(model="claude-sonnet-4-6"))
# Now 13 evaluators: 12 instant/free + 1 LLM-based
summary = suite.evaluate(trace, expected)
```

Use cases where deterministic evaluators fall short:
- **Evidence grounding** — Is "France GDP is $3.05T" recalled from training or fabricated? The judge can cross-reference the claim against tool results with semantic understanding, not just regex
- **Semantic policy violation** — Deterministic check catches "competitor products" literally. The judge catches "our rival's offering" or "the other platform"
- **Reasoning coherence** — Did the agent's multi-step reasoning actually make sense, or did it reach the right answer through flawed logic?
- **Output quality** — Beyond substring matching: is the final answer well-structured, complete, and appropriate for the task?

Trade-offs (why it's opt-in, not default):
- Non-deterministic — same trace may get different scores on different runs
- Adds latency (2-5s per evaluation) and API cost
- Requires an API key for the judge model
- The deterministic evaluators cover 80% of cases — the judge is for the nuanced 20%

## Proxy Server Improvements

### Trace Naming
Allow naming traces via header (`X-AgentLens-Trace: pharma-run-001`) or query param, so saved files have meaningful names instead of random hex IDs.

### Multi-Trace Support
Currently one active trace at a time. Support concurrent traces via trace ID headers for multi-agent systems where agents run in parallel.

### Streaming Support
The proxy currently buffers full responses. Add SSE/streaming passthrough for `stream=true` requests, accumulating the streamed chunks into a single span.

## Evaluator Improvements

### Number Provenance Chain
Track which numbers in LLM outputs can be traced back to specific tool results. Build a provenance graph: `tool_result["$3.05T"] → llm_output["$3.05 trillion"] → grounded`.

### Semantic Loop Detection
Current LoopDetector uses exact input hash matching. Add optional semantic similarity (embedding-based) to detect near-duplicate requests that use slightly different wording.

### Cost Model Configuration
Current cost estimation uses hardcoded rates ($0.01/1K input, $0.03/1K output). Allow configuring per-model pricing via a config file or CLI flag.

## Example Improvements

### Pharma Pipeline with Real Tool Execution
Extend `examples/pharma_pipeline/` to actually run RDKit feature engineering and sklearn training, with tools like `read_baseline`, `run_experiment`, `check_results` that the agents invoke through the proxy.

---

## Observability Gap Analysis (from industry research + pharma_pipeline result.log)

### Findings from pharma_pipeline Run

The pharma pipeline log (`examples/pharma_pipeline/result.log`) reveals concrete gaps in trace capture:

1. **Token usage shows 0in/0out** — The proxy captures token counts from the canned/mock response `usage` field, but when proxying to a real provider (or when CrewAI's internal routing doesn't pass usage back), tokens show as 0. This makes the Cost evaluator useless in real scenarios.
2. **Per-span duration shows 0ms** — All 3 spans show `(0ms)` in the trajectory timeline, even though total trace duration is 89s. The span start/end timestamps aren't being set from actual wall-clock time during proxy pass-through.
3. **Only 3 LLM_CALL spans for a 3-agent crew** — No tool_call spans captured because CrewAI didn't use tools in this scenario. But more importantly, there's no visibility into CrewAI's *inter-agent delegation* (task handoffs between ML Scientist → ML Engineer → Experiment Evaluator).
4. **Task field captured CrewAI boilerplate** — The task string includes "This is the expected criteria for your final answer..." framework noise instead of the clean task description.
5. **No agent identity per span** — All 3 LLM calls show as `llm_call` with no indication of which CrewAI agent made which call. In a multi-agent system, knowing *who* called *what* is critical.

---

## Priority 1 — Critical Gaps (blocks portfolio credibility)

### P1.1: Fix Span Timestamps (Bug)
**Problem:** Per-span duration shows 0ms while total trace duration is 89s.
**Root cause:** Likely the proxy sets `start_time = end_time = now()` instead of tracking actual request/response timing.
**Fix:** In `proxy.py`, capture `start_time` before forwarding/canned lookup and `end_time` after response is received.
**Reference:** Every platform (LangSmith, Langfuse, Braintrust, Phoenix) gets this right. A trajectory timeline with all 0ms durations looks broken.

### P1.2: Fix Token Usage Capture
**Problem:** Tokens show 0in/0out when proxying real providers.
**Root cause:** Token counts come from `CannedResponse.usage` in mock mode, but in proxy mode the real provider's usage field may not be parsed/mapped correctly. Also CrewAI may not forward usage through its internal LLM wrapper.
**Fix:** In proxy mode, parse the upstream response's `usage` field. In mock mode, estimate tokens from message length if canned usage is default zeros.
**Reference:** LangSmith, Langfuse, Braintrust all capture real token usage. OTel defines `gen_ai.usage.input_tokens` and `gen_ai.usage.output_tokens` as standard attributes.

### P1.3: Agent Identity per Span
**Problem:** In multi-agent systems, all spans show as generic `llm_call` with no way to tell which agent made the call.
**Approach:** Capture agent identity from request metadata. Options:
- Parse `system` message for agent name/role (CrewAI always includes role in system prompt)
- Accept `X-AgentLens-Agent` header for explicit tagging
- Add `agent_name` field to Span metadata
**Reference:** OTel GenAI conventions define `gen_ai.agent.id`, `gen_ai.agent.name`, `gen_ai.agent.description`. Phoenix has a dedicated Agent span type.

---

## Priority 2 — Important Gaps (strengthens portfolio story)

### P2.1: Retrieval/RAG Span Types
**Problem:** AgentLens has no `RETRIEVAL` or `EMBEDDING` span types. Every major platform (LangSmith, Langfuse, Phoenix, OTel) has them.
**Why it matters:** RAG is the most common agent pattern. An eval framework that can't evaluate retrieval quality misses a huge use case.
**Approach:** Add `SpanType.RETRIEVAL` and `SpanType.EMBEDDING`. Add RAG-specific evaluators:
- `RetrievalRelevanceEvaluator` — Are retrieved docs relevant to the query?
- `ContextFaithfulnessEvaluator` — Is the answer grounded in retrieved context?
**Reference:** Phoenix captures: query input, retrieved documents with IDs, relevance scores, content. RAGAS defines: faithfulness, answer relevancy, context precision, context recall.

### P2.2: Session/Conversation Grouping
**Problem:** AgentLens evaluates single traces. Multi-turn agent interactions (conversation with follow-ups, multi-step workflows with human-in-the-loop) have no grouping mechanism.
**Approach:** Add optional `session_id: str | None` field to Trace. Group traces by session for aggregate evaluation.
**Reference:** Langfuse groups via `sessionId`. OTel defines `gen_ai.conversation.id`. LangSmith groups via `project/thread`.

### P2.3: OTel-Compatible Export
**Problem:** AgentLens uses a custom span model. It cannot export traces to or import from OTel-compatible systems (Jaeger, Grafana Tempo, Datadog). This limits interop.
**Why it matters for portfolio:** Shows you understand production observability standards, not just building a toy.
**Approach:** Add an `otel` exporter module that maps AgentLens Trace/Span to OTel GenAI semantic conventions. Start with JSON export in OTel format, then optionally OTLP gRPC.
**Reference:** OTel GenAI conventions are in development status but already adopted by LangSmith, Langfuse, and Braintrust. Attributes: `gen_ai.operation.name`, `gen_ai.request.model`, `gen_ai.usage.*`, `gen_ai.tool.*`.

### P2.4: Dataset/Benchmark Management
**Problem:** No way to run evaluations over a test suite and track regression across versions. You evaluate one trace at a time.
**Why it matters:** Anthropic's agent guidance emphasizes iterative improvement via repeated evaluation. Every competitor has this.
**Approach:** Add a `benchmarks/` concept:
- `BenchmarkSuite` — A set of (task, expectations, optional reference trace) tuples
- `agentlens benchmark run <suite.json>` — Run all tasks, collect traces, evaluate
- `agentlens benchmark compare <run1> <run2>` — Compare two runs side-by-side
**Reference:** LangSmith datasets, Braintrust experiments, Langfuse experiments.

---

## Priority 3 — Nice-to-Have (future roadmap)

### P3.1: LLM-as-Judge Evaluator
*Already documented above in detail.* Every competitor has it. It's the most expected feature after deterministic evaluators. Keep it opt-in, call LLM directly (not through proxy).

### P3.2: Experiment Comparison (A/B)
Compare two agent runs (different models, prompts, or configs) over the same benchmark dataset. Show side-by-side scores, trajectory differences, cost comparison.
**Reference:** LangSmith experiments, Braintrust experiments.

### P3.3: Time-to-First-Token (TTFT) Metric
**Problem:** AgentLens only tracks total span latency. For streaming-capable proxies, TTFT is a key UX metric.
**Reference:** OTel defines `gen_ai.server.time_to_first_token` as a standard histogram metric.

### P3.4: Content Privacy Controls
**Problem:** AgentLens captures full prompt/response content by default. Production use may require redaction.
**Approach:** Add `--redact-content` flag to proxy that strips message content from traces, keeping only metadata (token counts, timing, tool names).
**Reference:** OTel GenAI conventions have explicit opt-in for sensitive content capture. Langfuse has privacy controls.

### P3.5: Human Annotation Workflow
Allow humans to score traces via a simple web UI or API. Track human vs automated evaluator agreement.
**Reference:** Langfuse and LangSmith both support human feedback loops.

### P3.6: Online/Production Scoring
Score live traffic in real-time as it flows through the proxy. Currently AgentLens is offline-only (evaluate after the fact).
**Reference:** All major platforms (LangSmith, Langfuse, Braintrust) support this.

### P3.7: Adaptive Reasoning Quality
**Problem:** Anthropic stresses that agents should self-assess using tool results. AgentLens does not evaluate whether the agent *used* tool results to adjust its plan.
**Approach:** Check if LLM_CALL spans after TOOL_CALL spans reference or react to the tool output. Score higher if the agent adapts its approach based on tool feedback.
**Reference:** Anthropic "Building Effective Agents" guide: agents should "gain ground truth from the environment at each step."

---

## Comparison Matrix: AgentLens vs Industry

| Capability | LangSmith | Langfuse | Braintrust | Phoenix | OTel | **AgentLens** |
|---|---|---|---|---|---|---|
| LLM call spans | Y | Y | Y | Y | Y | **Y** |
| Tool call spans | Y | Y | Y | Y | Y | **Y** |
| Retrieval/RAG spans | Y | Y | Y | Y | Y | **N** (P2.1) |
| Embedding spans | Y | Y | - | Y | Y | **N** (P2.1) |
| Nested span hierarchy | Y | Y | Y | Y | Y | **Y** (parent_id) |
| Session grouping | Y | Y | Y | - | Y | **N** (P2.2) |
| Token usage tracking | Y | Y | Y | Y | Y | **Y** (buggy P1.2) |
| Cost estimation | Y | Y | Y | - | N | **Y** |
| Latency per span | Y | Y | Y | Y | Y | **Y** (buggy P1.1) |
| TTFT / per-token latency | - | - | - | - | Y | **N** (P3.3) |
| Agent identity per span | Y | Y | Y | Y | Y | **N** (P1.3) |
| LLM-as-judge | Y | Y | Y | Y | - | **N** (P3.1) |
| Human annotation | Y | Y | Y | - | - | **N** (P3.5) |
| Deterministic evaluators | Y | Y | Y | Y | - | **Y** (12 built-in) |
| **Loop/retry detection** | - | - | - | - | - | **Y** (unique) |
| **Unauthorized action detection** | - | - | - | - | - | **Y** (unique) |
| **Policy violation detection** | - | - | - | - | - | **Y** (unique) |
| **Hallucination flagging** | - | - | - | - | - | **Y** (unique) |
| **Step efficiency scoring** | - | - | - | - | - | **Y** (unique) |
| **Tool selection quality** | - | - | - | - | - | **Y** (unique) |
| Online scoring | Y | Y | Y | Y | - | **N** (P3.6) |
| Experiment comparison | Y | Y | Y | - | - | **N** (P3.2) |
| Dataset management | Y | Y | Y | - | - | **N** (P2.4) |
| OTel export | Y | Y | Y | Y | native | **N** (P2.3) |
| Content privacy | - | Y | - | - | Y | **N** (P3.4) |
| **Provider-agnostic proxy** | - | - | - | - | - | **Y** (unique) |
| **Mailbox mode** | - | - | - | - | - | **Y** (planned, unique) |

**Key takeaway:** AgentLens has 6 evaluators NO major platform offers + unique proxy architecture. The P1 bugs need fixing for credibility. P2 items would make it a serious contender. P3 is stretch goal territory.
