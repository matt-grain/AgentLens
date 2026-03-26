"""
AgentLens + CrewAI Integration Example

Demonstrates how to capture and evaluate CrewAI agent trajectories
using the AgentLens proxy server in mock mode.

Usage:
    # Terminal 1: Start the proxy
    uv run agentlens serve --mode mock

    # Terminal 2: Run this script
    uv run python examples/crewai_research/run.py
"""

from __future__ import annotations

import sys

import httpx

PROXY_BASE = "http://localhost:8650"
PROXY_V1 = f"{PROXY_BASE}/v1"


def _check_proxy() -> bool:
    """Return True if the AgentLens proxy is reachable."""
    try:
        response = httpx.get(f"{PROXY_BASE}/health", timeout=3.0)
        return response.status_code == 200
    except httpx.ConnectError:
        return False


def _run_crew() -> None:
    """Configure and run a two-agent CrewAI crew pointed at the AgentLens proxy."""
    # Import here so the module is usable even without crewai installed
    # (the proxy check above gives a clear error before we reach this).
    from crewai import LLM, Agent, Crew, Task

    # Point CrewAI at the AgentLens proxy.  Mock mode accepts any api_key.
    proxy_llm = LLM(
        model="openai/gpt-4o-mini",
        base_url=PROXY_V1,
        api_key="agentlens-mock",
        temperature=0.0,
        timeout=30.0,
    )

    researcher = Agent(
        role="Research Analyst",
        goal="Find accurate economic data and statistics",
        backstory=(
            "You are a meticulous research analyst who specialises in macroeconomics. "
            "You always cite your sources and flag uncertainty."
        ),
        llm=proxy_llm,
        max_iter=3,
        allow_delegation=False,
        verbose=True,
    )

    writer = Agent(
        role="Report Writer",
        goal="Synthesise research findings into clear, concise reports",
        backstory=(
            "You are a senior business writer who transforms raw data into "
            "executive-ready summaries. You are precise and never fabricate numbers."
        ),
        llm=proxy_llm,
        max_iter=3,
        allow_delegation=False,
        verbose=True,
    )

    research_task = Task(
        description=(
            "Research the GDP of France in 2023 and compare it with Germany. "
            "Include nominal GDP figures in USD, growth rates, and any notable differences."
        ),
        expected_output=(
            "A structured summary containing: France GDP 2023 (USD), "
            "Germany GDP 2023 (USD), year-on-year growth rates for both, "
            "and a one-paragraph comparison."
        ),
        agent=researcher,
    )

    writing_task = Task(
        description=(
            "Using the research findings, write a concise comparison report "
            "suitable for a non-specialist audience. Keep it under 200 words."
        ),
        expected_output="A polished, professional comparison report in plain prose.",
        agent=writer,
        context=[research_task],
    )

    crew = Crew(
        agents=[researcher, writer],
        tasks=[research_task, writing_task],
        verbose=True,
    )

    # The mock server returns canned responses, so CrewAI may raise an error
    # when it tries to parse them.  We catch it and proceed to trace evaluation.
    try:
        result = crew.kickoff()
        print("\n--- Crew output ---")
        print(result)
    except Exception as exc:  # noqa: BLE001
        print(f"\n[AgentLens] Crew raised an exception (expected with mock mode): {exc}")
        print("[AgentLens] Proceeding to evaluate whatever traces were captured.\n")


def _evaluate_traces() -> None:
    """Finalise the trace, fetch it, and run AgentLens evaluators."""
    from agentlens.engine import EvaluationSuite
    from agentlens.models.expectation import TaskExpectation
    from agentlens.models.trace import Trace
    from agentlens.report.terminal import print_report

    # Finalize: flush in-flight spans into a completed Trace object.
    httpx.post(f"{PROXY_BASE}/traces/reset")

    response = httpx.get(f"{PROXY_BASE}/traces")
    response.raise_for_status()
    traces_data: list[dict] = response.json()  # type: ignore[type-arg]

    if not traces_data:
        print("[AgentLens] No traces captured — did the proxy receive any LLM calls?")
        return

    suite = EvaluationSuite()
    expected = TaskExpectation(
        expected_output="GDP",
        # The mock server does not return real tool calls, so we keep
        # expected_tools empty to avoid penalising the trace unfairly.
        forbidden_tools=["send_email", "delete_file"],
        max_steps=20,
    )

    for trace_data in traces_data:
        trace = Trace.model_validate(trace_data)
        summary = suite.evaluate(trace, expected)
        print_report(summary, trace, verbose=True)


def main() -> None:
    if not _check_proxy():
        print(
            "[AgentLens] ERROR: Proxy is not running.\nStart it first with:\n\n    uv run agentlens serve --mode mock\n"
        )
        sys.exit(1)

    print("[AgentLens] Proxy is up. Running CrewAI workflow...\n")
    _run_crew()

    print("\n[AgentLens] Evaluating captured traces...\n")
    _evaluate_traces()


if __name__ == "__main__":
    main()
