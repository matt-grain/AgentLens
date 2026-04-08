# AgentLens

**Trajectory-first agent evaluation framework.**

![Python](https://img.shields.io/badge/python-3.13-blue) ![License](https://img.shields.io/badge/license-MIT-green) ![Tests](https://img.shields.io/badge/tests-138%20passing-brightgreen)

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

Point any agent at `http://localhost:8650` via `OPENAI_API_BASE` and traces are captured automatically. The proxy never runs tools or modifies messages — it just observes the conversation. Three modes: **mock** (canned responses, zero cost), **proxy** (forwards to real LLM), **mailbox** (queues for external brain). Optional **guards** add real-time evaluation hooks that can warn, block, or escalate responses before they reach the agent.

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
uv run agentlens serve --mode proxy --proxy-to https://api.openai.com --guards guards.yaml  # with real-time guards
```

Export a trace in OpenTelemetry format (for Jaeger, Grafana Tempo, Datadog):

```bash
uv run agentlens export-otel traces/abc123.json -o trace_otel.json
```

Run a benchmark suite (aggregate evaluation over multiple traces):

```bash
uv run agentlens benchmark benchmarks/default.json
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

## Why Another Tool?

Existing observability platforms (LangSmith, Langfuse, Braintrust) do **passive observation** — they record what happened. AgentLens does **interactive observation** — you can intervene in the flow.

### The Mailbox as an Agent Debugger

The mailbox mode turns AgentLens into a **debugger for agent orchestration**. Like setting breakpoints in code, but for multi-agent LLM workflows:

- **Replay scenarios** — same agent config, same task, but you control the LLM responses
- **Inspect raw prompts** — see exactly what CrewAI/AutoGen/LangChain sends to the LLM (system prompt, tool definitions, inter-agent context)
- **Test failure modes** — "what if the LLM hallucinated here? Does the framework recover or spiral?"
- **Step through the flow** — one request at a time, inspecting each agent's prompt before answering

No other eval framework offers this. Every competitor watches from the outside. AgentLens lets you sit inside the conversation.

### Guards: Real-Time Evaluation Hooks

Guards transform AgentLens from observer to **circuit breaker**. When enabled, the proxy evaluates each LLM response *before* returning it to the agent, using the same deterministic evaluators — but in real time.

```yaml
# guards.yaml
enabled: true
rules:
  - evaluator_name: hallucination_flag
    threshold: 0.5
    action: warn        # append warning to response
  - evaluator_name: policy_violation
    threshold: 1.0
    action: block       # replace response with rejection
  - evaluator_name: loop_detector
    threshold: 0.5
    action: warn
  - evaluator_name: unauthorized_action
    threshold: 1.0
    action: escalate    # route to mailbox for human review
```

Three intervention levels:

| Action | Behavior |
|--------|----------|
| **warn** | Appends evaluation warning to the LLM response. Agent sees it as part of the output. |
| **block** | Replaces the response entirely. Agent thinks the LLM refused. |
| **escalate** | Routes to mailbox for human review before returning (requires mailbox or auto-creates one). |

The agent never knows it's being evaluated — the proxy remains invisible at the protocol level. This is critical for pharma and regulated environments where you want to **prevent** bad outputs, not just detect them after.

#### Choosing Guard Actions: What Happens in Practice

Guards are invisible to the agent framework — but the framework still has to process whatever the guard returns. Each action has different consequences depending on how the orchestrator (CrewAI, AutoGen, LangChain, etc.) handles unexpected responses.

**WARN** — safest for most cases:

The LLM response is returned normally with a warning appended. The orchestrator parses the response as usual. On the **next** LLM call, the warning is part of the conversation history, so the LLM sees it and can self-correct.

```
LLM response:  "The compound has 87% oral bioavailability."
Guard appends: "[GUARD WARNING: Unverified numeric claim without tool evidence]"
→ CrewAI parses the response normally (output format intact)
→ On next turn, the LLM reads the warning and may verify the claim via a tool call
```

**BLOCK** — for hard safety boundaries:

The original response is replaced entirely. The orchestrator receives text like *"I need to reconsider this approach."* instead of the expected structured output. In CrewAI, this means:

1. The agent tries to parse the response as its expected output format → **fails**
2. CrewAI retries with the original prompt + an error message (*"Wrong tool output format"*)
3. The LLM generates a **new** response — which may not repeat the violation
4. After `max_iter` retries without success → the task fails

This is a valid safety outcome: **retry and self-correct, or fail safely** rather than act on a policy violation. Reserve BLOCK for things that should never pass through (e.g., forbidden tool use, dangerous code patterns).

**ESCALATE** — the pharma answer:

The response is held in the mailbox until a human expert reviews it. The orchestrator's HTTP call simply **blocks** (waits) until the human approves, modifies, or rejects the response. From CrewAI's perspective, the LLM is just slow — no parsing errors, no retries. The human sees the full prompt, the LLM's proposed response, and the evaluation flag, then decides what to return.

```
Agent → proxy → LLM responds → guard flags policy violation → mailbox holds response
                                                                  ↓
                                              Human expert reviews: "The proposed hypothesis
                                              uses a deprecated assay method. Rejecting."
                                                                  ↓
                                              Agent receives rejection → proposes alternative
```

**Recommended configuration for regulated environments (pharma, finance):**

```yaml
rules:
  # Soft signals: warn and let the agent self-correct
  - evaluator_name: hallucination_flag
    threshold: 0.5
    action: warn

  - evaluator_name: loop_detector
    threshold: 0.5
    action: warn

  # Hard safety: block immediately
  - evaluator_name: policy_violation
    threshold: 1.0
    action: block

  # Critical decisions: human in the loop
  - evaluator_name: unauthorized_action
    threshold: 1.0
    action: escalate
```

### Framework-Agnostic by Architecture

AgentLens speaks the **OpenAI-compatible API** — the de facto standard. Any agent framework that can set a base URL works without code changes:

| Framework | Integration |
|-----------|------------|
| CrewAI | `LLM(base_url="http://localhost:8650/v1")` |
| AutoGen | `config_list=[{"base_url": "http://localhost:8650/v1"}]` |
| LangChain | `ChatOpenAI(base_url="http://localhost:8650/v1")` |
| Raw OpenAI SDK | `openai.Client(base_url="http://localhost:8650/v1")` |
| Any HTTP client | `POST http://localhost:8650/v1/chat/completions` |

No SDK wrappers, no monkey-patching, no framework plugins. One proxy, any agent.

### Comparison

| Capability | LangSmith | Langfuse | Braintrust | **AgentLens** |
|---|---|---|---|---|
| LLM + tool span capture | Y | Y | Y | **Y** |
| RAG/embedding spans | Y | Y | Y | **Y** |
| Session grouping | Y | Y | Y | **Y** |
| Token usage + cost | Y | Y | Y | **Y** |
| OTel export | Y | Y | Y | **Y** |
| Benchmark suites | Y | Y | Y | **Y** |
| LLM-as-judge | Y | Y | Y | N (roadmap) |
| Human annotation | Y | Y | - | N (roadmap) |
| **Loop/retry detection** | - | - | - | **Y** (unique) |
| **Unauthorized action detection** | - | - | - | **Y** (unique) |
| **Policy violation detection** | - | - | - | **Y** (unique) |
| **Hallucination flagging** | - | - | - | **Y** (unique) |
| **Step efficiency scoring** | - | - | - | **Y** (unique) |
| **Tool selection quality** | - | - | - | **Y** (unique) |
| **RAG grounding evaluator** | - | - | - | **Y** (unique) |
| **Agent identity extraction** | - | - | - | **Y** (unique) |
| **Provider-agnostic proxy** | - | - | - | **Y** (unique) |
| **Mailbox mode (agent debugger)** | - | - | - | **Y** (unique) |
| **Real-time guard hooks** | - | - | - | **Y** (unique) |

AgentLens has **11 capabilities no major platform offers** — 8 unique evaluators + the proxy/mailbox architecture. It's not a replacement for LangSmith (which excels at production monitoring) — it fills the gap between "build an agent" and "know if the agent is good."

| Tool | Focus | Best For |
|------|-------|----------|
| **AgentLens** | Agent trajectory evaluation + debugging | Development, testing, CI gates |
| RAGAS | RAG pipeline quality | RAG-specific faithfulness/relevance |
| DeepEval | LLM output quality | Output correctness scoring |
| LangSmith | Production observability | Monitoring live traffic at scale |

## Development

Built with [Anima](https://github.com/matt-grain/Anima) (long-term memory for AI-assisted development) following the practices documented in [AgenticDevelopmentBestPractices](https://github.com/matt-grain/AgenticDevelopmentBestPractices).
