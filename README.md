# AgentLens

**Trajectory-first agent evaluation framework.**

![Python](https://img.shields.io/badge/python-3.13-blue) ![License](https://img.shields.io/badge/license-MIT-green) ![Tests](https://img.shields.io/badge/tests-123%20passing-brightgreen)

## The Problem

Most people evaluate LLM agents like chatbots — check the final answer and move on. But agents don't just produce outputs, they follow **trajectories**: planning steps, tool calls, retries, and branching paths. Evaluating the final answer alone misses wasteful loops, unauthorized tool use, hallucinated claims without evidence, and cost overruns.

AgentLens evaluates the **full trajectory** at four levels: business goals, behavioral efficiency, risk, and operational performance. All 14 evaluators are deterministic — no LLM-as-judge, instant results, zero cost.

![Pharma example](https://github.com/matt-grain/AgentLens/blob/main/examples/pharma_pipeline/report_screenshot.png?raw=true)

## Quick Start

```bash
uv pip install -e .
uv run agentlens demo
```

No API keys required — the demo runs on pre-recorded fixtures.

## How It Works

The proxy sits between the agent framework and the LLM, capturing every exchange:

```
Agent (CrewAI, etc.)              AgentLens Proxy                    LLM
  │                                     │                             │
  │  1. POST /v1/chat/completions       │                             │
  │     {prompt, tools, messages}  ───> │  ── captures LLM_CALL ──>   │
  │                                     │                             │
  │                                     │  <── response ──            │
  │  2. Response: "call search(         │  ── captures TOOL_CALL ──>  │
  │     query='France GDP')"      <───  │                             │
  │                                     │                             │
  │  3. Agent runs search locally       │                             │
  │     (proxy doesn't see this)        │                             │
  │                                     │                             │
  │  4. POST /v1/chat/completions       │                             │
  │     {tool result: "$3.05T"}   ───>  │  ── captures LLM_CALL ──>   │
  │                                     │                             │
  │  5. Response: final answer    <───  │  ── captures output ──>     │
  │                                     │                             │
  │                          Trace = [LLM_CALL, TOOL_CALL, LLM_CALL]  │
  │                                     │                             │
  │                              Evaluate → Report                    │
```

Point any agent at `http://localhost:8650` via `OPENAI_API_BASE` and traces are captured automatically. The proxy never runs tools or modifies messages — it just observes the conversation. Three modes: **mock** (canned responses, zero cost), **proxy** (forwards to real LLM), **mailbox** (queues for external brain).

## 4-Level Evaluation Framework

| Level | What It Measures | Evaluators |
|-------|-----------------|------------|
| Business | Goal achievement | TaskCompletion, HumanHandoff |
| Behavior | Path efficiency | ToolSelection, StepEfficiency, LoopDetector, Recovery |
| Risk | Safety | UnauthorizedAction, HallucinationFlag, PolicyViolation |
| Operational | Performance and cost | Latency, Cost, Variance |

Level weights in the overall score: Business 30%, Behavior 30%, Risk 25%, Operational 15%.

### Design Choice: Deterministic Evaluation, No LLM-as-Judge

All 14 evaluators are rule-based and deterministic. There are no LLM calls in the evaluation pipeline — results are instant, free, and reproducible.

This means some evaluators flag **signals**, not definitive verdicts:

- **HallucinationFlag** detects **unverified numeric claims** — the agent cited a number (e.g., "$3.05 trillion", "47%") without a preceding tool call that could have sourced it. This is better understood as "lack of evidence in the trace" rather than confirmed hallucination. The LLM might be correct from training data — but the trace shows no tool-based evidence for the claim. In agent evaluation, knowing that an agent asserted numbers without grounding them in tool results is a useful signal regardless.
- **PolicyViolation** uses simple substring matching against a list of forbidden phrases — it catches obvious violations but won't detect paraphrased or subtle policy breaches.
- **LoopDetector** fingerprints spans by (type, name, input hash) — it catches exact duplicates and cycles but not semantically similar retries with slightly different inputs.

Where deterministic evaluation falls short, LLM-as-judge would complement it — but at the cost of non-determinism, latency, and API spend. AgentLens prioritizes fast, reproducible signals that work at scale.

## Demo Output

```
=== Scenario: happy_path ===
───────────────────────── AgentLens Evaluation Report ─────────────────────────
Task: What was the GDP of France in 2023 and how does it compare to Germany?
Agent: research-assistant  |  Trace: trace_happy_001
Duration: 2300ms  |  Steps: 6
Tokens: 130in / 70out
Overall Score: 98%

          Level Scores
┌─────────────┬───────┬────────┐
│ Level       │ Score │ Status │
├─────────────┼───────┼────────┤
│ Business    │  100% │  PASS  │
│ Behavior    │  100% │  PASS  │
│ Risk        │  100% │  PASS  │
│ Operational │   90% │  PASS  │
└─────────────┴───────┴────────┘

Trajectory Timeline
  ✓  plan  (400ms)
  ✓  search  (100ms)
  ✓  search  (100ms)
  ✓  calculator  (50ms)
  ✓  synthesize  (500ms)
  ✓  cite_source  (50ms)
```

## CLI Commands

Run the pre-recorded demo (all three scenarios):

```bash
uv run agentlens demo
```

Run a specific scenario:

```bash
uv run agentlens demo --scenario loop
```

Generate an HTML report alongside the terminal output:

```bash
uv run agentlens demo --html --output report.html
```

Evaluate any trace JSON file:

```bash
uv run agentlens evaluate path/to/trace.json
uv run agentlens evaluate path/to/trace.json --expectations path/to/expectations.json
uv run agentlens evaluate path/to/trace.json --html --output report.html
```

Start the proxy server:

```bash
uv run agentlens serve                                          # mock mode (canned responses)
uv run agentlens serve --mode proxy --proxy-to https://api.openai.com  # forward to real LLM
uv run agentlens serve --mode mailbox --traces-dir traces       # mailbox mode (external brain)
uv run agentlens serve --mode mailbox --timeout 120             # custom timeout (default 300s)
```

## Writing Custom Evaluators

Implement the `Evaluator` protocol — a name, a level, and an `evaluate` method:

```python
from agentlens import Evaluator, EvaluationSuite
from agentlens.models.evaluation import EvalLevel, EvalResult, EvalSeverity

class CitationRateEvaluator:
    name = "citation_rate"
    level = EvalLevel.BEHAVIOR

    def evaluate(self, trace, expected=None):
        cited = sum(1 for s in trace.spans if s.name == "cite_source")
        score = min(cited / 3, 1.0)
        return [EvalResult(
            evaluator_name=self.name, level=self.level,
            score=score, passed=score >= 0.5,
            message=f"{cited} citations found",
            severity=EvalSeverity.WARNING if score < 0.5 else EvalSeverity.INFO,
        )]

suite = EvaluationSuite()
suite.add_evaluator(CitationRateEvaluator())
```

## Integration

Point any OpenAI-compatible agent at the AgentLens proxy by setting the base URL before running:

```bash
uv run agentlens serve &
export OPENAI_API_BASE=http://localhost:8650/v1
# run your agent as normal
curl http://localhost:8650/traces        # list captured traces
curl -X POST http://localhost:8650/traces/reset  # finalize current trace
```

After execution, retrieve traces from `/traces` and feed them to `EvaluationSuite.evaluate()`. Traces are also auto-saved to `./traces/` as JSON files by default.

## Using with Agentic Development Tools

The **mailbox mode** enables any AI coding assistant to act as the LLM brain for an agent under evaluation. This works with Claude Code, OpenCode, GitHub Copilot, Cursor, or any tool that can make HTTP calls.

```bash
# Terminal 1 — start proxy in mailbox mode
uv run agentlens serve --mode mailbox

# Terminal 2 — run the agent under evaluation
uv run python examples/pharma_pipeline/run.py
```

The agent's LLM calls queue in the mailbox. In your AI coding assistant session:

```
"Poll http://localhost:8650/mailbox for pending requests.
 For each request, read GET /mailbox/{id} to see the full prompt and tools.
 Reason about the best response, then POST /mailbox/{id} with your answer.
 Keep polling until idle for 30 seconds."
```

The assistant reads each agent's prompt, reasons about it, and submits a response — becoming the LLM brain. AgentLens captures the full trajectory for evaluation. This is useful for:

- **Debugging agent behavior** — watch exactly what prompts your agent sends and how it reacts to responses
- **Testing with a real LLM** without paying for API calls on every test run — use the mailbox with a local model or coding assistant
- **Human-in-the-loop evaluation** — a domain expert can answer the mailbox requests manually to test agent robustness

See `examples/mailbox_brain/` for a standalone brain script and `examples/pharma_pipeline/README.md` for a step-by-step walkthrough.

## Examples

| Example | Agents | What It Demonstrates |
|---------|--------|---------------------|
| `examples/crewai_research/` | 2 (Researcher, Writer) | Basic CrewAI integration with proxy |
| `examples/pharma_pipeline/` | 3 (ML Scientist, ML Engineer, Evaluator) | Multi-agent ML experiment evaluation |
| `examples/mailbox_brain/` | N/A | Standalone brain script for mailbox mode |

## Why AgentLens

| Tool | Focus | Approach |
|------|-------|----------|
| AgentLens | Agent trajectories | Deterministic, rule-based evaluators |
| RAGAS | RAG pipeline quality | LLM-as-judge for faithfulness/relevance |
| DeepEval | LLM output quality | LLM-as-judge for correctness |

AgentLens is not a replacement for RAGAS or DeepEval — it fills the gap they leave: **did the agent take the right path?** All 14 evaluators are deterministic (no LLM calls), making evaluations instant, free, and reproducible in CI.

## Development

Built with [Anima](https://github.com/matt-grain/Anima) (long-term memory for AI-assisted development) following the practices documented in [AgenticDevelopmentBestPractices](https://github.com/matt-grain/AgenticDevelopmentBestPractices).
