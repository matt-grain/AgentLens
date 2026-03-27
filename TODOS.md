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

## Priority 1 — Critical Gaps ~~(blocks portfolio credibility)~~ DONE

### P1.1: Fix Span Timestamps ~~(Bug)~~ DONE
~~**Problem:** Per-span duration shows 0ms while total trace duration is 89s.~~
**Fixed:** `collector.py` now accepts `start_time` before the request and sets `end_time` after response. Spans show real wall-clock durations (e.g., 17s, 37s, 27s in mailbox mode).

### P1.2: Fix Token Usage Capture — DONE
~~**Problem:** Tokens show 0in/0out when proxying real providers.~~
**Fixed:** Mailbox mode estimates tokens from message char count (~4 chars/token heuristic). Mock mode uses canned usage. Proxy mode parses upstream response. Cost evaluator now gives meaningful scores.

### P1.3: Agent Identity per Span — DONE
~~**Problem:** In multi-agent systems, all spans show as generic `llm_call`.~~
**Fixed:** `_extract_agent_name()` parses "You are {Role}." from CrewAI system messages. Stored in `span.metadata["agent_name"]`. Displayed in terminal (`[ML Scientist] llm_call`) and HTML reports. Also accepts `X-AgentLens-Agent` header for explicit tagging.

---

## Priority 2 — Important Gaps ~~(strengthens portfolio story)~~ DONE

### P2.1: Retrieval/RAG Span Types — DONE
~~**Problem:** AgentLens has no `RETRIEVAL` or `EMBEDDING` span types.~~
**Fixed:** Added `SpanType.RETRIEVAL` and `SpanType.EMBEDDING`. Two new evaluators:
- `RetrievalRelevanceEvaluator` — scores doc relevance (score >= 0.5 threshold)
- `ContextGroundingEvaluator` — checks if LLM output is grounded in retrieved docs (3-word phrase overlap)
Both gracefully handle non-RAG traces (return INFO, don't penalize). 14 evaluators total.

### P2.2: Session/Conversation Grouping — DONE
~~**Problem:** No grouping for multi-turn traces.~~
**Fixed:** `Trace.session_id: str | None` field. Proxy reads `X-AgentLens-Session` header. CLI `--session` option on serve command. `TraceCollector.set_session_id()` for per-request override.

### P2.3: OTel-Compatible Export — DONE
~~**Problem:** No interop with OTel systems.~~
**Fixed:** `src/agentlens/export/otel.py` maps Trace/Span to OTel GenAI semantic conventions (JSON). CLI: `agentlens export-otel trace.json -o otel.json`. Pure stdlib, no OTel dependency. Maps all span types, token usage, agent names, session IDs.

### P2.4: Dataset/Benchmark Management — DONE (run only, no comparison yet)
~~**Problem:** Evaluate one trace at a time.~~
**Fixed:** `src/agentlens/benchmark.py` with `BenchmarkSuite`, `BenchmarkCase`, `BenchmarkResult`. CLI: `agentlens benchmark benchmarks/default.json`. Ships with 3-case default suite. Aggregate scores by level. Comparison (`benchmark compare`) deferred to P3.2.

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
| Retrieval/RAG spans | Y | Y | Y | Y | Y | **Y** ~~(P2.1)~~ |
| Embedding spans | Y | Y | - | Y | Y | **Y** ~~(P2.1)~~ |
| Nested span hierarchy | Y | Y | Y | Y | Y | **Y** (parent_id) |
| Session grouping | Y | Y | Y | - | Y | **Y** ~~(P2.2)~~ |
| Token usage tracking | Y | Y | Y | Y | Y | **Y** ~~(fixed P1.2)~~ |
| Cost estimation | Y | Y | Y | - | N | **Y** |
| Latency per span | Y | Y | Y | Y | Y | **Y** ~~(fixed P1.1)~~ |
| TTFT / per-token latency | - | - | - | - | Y | **N** (P3.3) |
| Agent identity per span | Y | Y | Y | Y | Y | **Y** ~~(P1.3)~~ |
| LLM-as-judge | Y | Y | Y | Y | - | **N** (P3.1) |
| Human annotation | Y | Y | Y | - | - | **N** (P3.5) |
| Deterministic evaluators | Y | Y | Y | Y | - | **Y** (14 built-in) |
| **Loop/retry detection** | - | - | - | - | - | **Y** (unique) |
| **Unauthorized action detection** | - | - | - | - | - | **Y** (unique) |
| **Policy violation detection** | - | - | - | - | - | **Y** (unique) |
| **Hallucination flagging** | - | - | - | - | - | **Y** (unique) |
| **Step efficiency scoring** | - | - | - | - | - | **Y** (unique) |
| **Tool selection quality** | - | - | - | - | - | **Y** (unique) |
| Online scoring | Y | Y | Y | Y | - | **N** (P3.6) |
| Experiment comparison | Y | Y | Y | - | - | **N** (P3.2) |
| Dataset management | Y | Y | Y | - | - | **Y** ~~(P2.4)~~ |
| OTel export | Y | Y | Y | Y | native | **Y** ~~(P2.3)~~ |
| Content privacy | - | Y | - | - | Y | **N** (P3.4) |
| **Provider-agnostic proxy** | - | - | - | - | - | **Y** (unique) |
| **Mailbox mode** | - | - | - | - | - | **Y** (unique) |
| **RAG grounding evaluator** | - | - | - | - | - | **Y** (unique) |

**Key takeaway:** P1 bugs fixed, P2 features shipped. AgentLens now has 8 evaluators NO major platform offers + unique proxy/mailbox architecture. P3 items are stretch goals for future iterations.
