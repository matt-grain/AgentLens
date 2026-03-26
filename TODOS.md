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
