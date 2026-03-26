# CrewAI + AgentLens Example

This example shows how to evaluate a CrewAI multi-agent workflow using the
AgentLens proxy server. It demonstrates the core insight behind AgentLens:
**any agent framework can be evaluated simply by pointing it at the proxy** —
no code changes to the framework itself.

## What This Example Does

1. Starts a two-agent CrewAI crew (Researcher + Writer).
2. Routes all LLM calls through the AgentLens proxy at `http://localhost:8650`.
3. The proxy captures every call as a structured `Trace` with typed `Span`s.
4. After the crew finishes, the script fetches the trace and runs the full
   AgentLens evaluator suite (business, behavior, risk, operational).
5. Prints a Rich terminal report showing scores and the trajectory timeline.

## Prerequisites

- Python 3.13+
- `uv` installed
- AgentLens installed (from the repo root: `uv sync`)
- CrewAI and httpx: `uv pip install crewai>=0.108.0 httpx`

## How to Run

**Terminal 1** — start the proxy in mock mode (no API key needed):

```bash
uv run agentlens serve --mode mock
```

**Terminal 2** — run the example:

```bash
uv run python examples/crewai_research/run.py
```

## What to Expect

Because the proxy returns canned responses, CrewAI may raise a parsing error
— that is expected and handled. The script will still evaluate whatever LLM
calls were captured before the error, printing something like:

```
AgentLens Evaluation Report
Task: Research the GDP of France ...
Agent: agentlens-proxy  |  Trace: abc123def456
Duration: 12ms  |  Steps: 3
Overall Score: 72%

Level Scores
Business  80%  PASS
Behavior  65%  PASS
Risk      75%  PASS
Operational 60% PASS

Trajectory Timeline
  ✓ [llm_call] llm_call  (4ms)
  ✓ [llm_call] llm_call  (3ms)
  ...
```

## Switching to a Real LLM

Replace the mock proxy with a real one that forwards to OpenAI:

```bash
# Terminal 1
OPENAI_API_KEY=sk-... uv run agentlens serve --mode proxy --proxy-to https://api.openai.com

# Terminal 2 (unchanged)
uv run python examples/crewai_research/run.py
```

The same evaluation code works without any changes — traces now contain real
token counts, latency data, and actual model responses.
