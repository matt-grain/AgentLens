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
Add a pluggable `LLMJudgeEvaluator` that calls a dedicated CrewAI agent for nuanced assessment:
- Configurable via `EvaluationSuite(llm_judge=True, judge_model="claude-sonnet-4-6")`
- The judge agent receives the full trace + expectations and produces a structured verdict
- Use cases where deterministic evaluators fall short:
  - Semantic policy violation (paraphrased forbidden content)
  - Output quality beyond substring matching
  - Reasoning coherence across multi-step trajectories
  - Detecting subtle hallucination vs. valid training-data recall
- Trade-off: non-deterministic, adds latency and cost — should be opt-in, not default
- Could use the mailbox pattern itself: AgentLens evaluates traces, and the judge is just another agent going through the proxy

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
