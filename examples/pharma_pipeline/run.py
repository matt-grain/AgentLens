"""
AgentLens + CrewAI: Pharma ML Pipeline Evaluation

3-agent workflow for molecular ML experiment iteration:
  1. ML Scientist — proposes feature engineering improvements
  2. ML Engineer — plans the implementation
  3. Evaluator — assesses feasibility and expected impact

AgentLens captures the full trajectory and evaluates agent behavior.

Usage:
    # Terminal 1: Start proxy (pick ONE mode)
    uv run agentlens serve --mode mock --scenario pharma_pipeline   # canned responses, zero cost
    uv run agentlens serve --mode mailbox                           # you/AI answer via /mailbox API
    uv run agentlens serve --mode proxy --proxy-to https://api.openai.com  # forward to real LLM

    # Terminal 2: Run pipeline (same command regardless of proxy mode)
    uv run python examples/pharma_pipeline/run.py

The script always calls localhost:8650. The proxy decides what happens — the agent never knows.
"""

from __future__ import annotations

import sys

import httpx

PROXY_URL = "http://localhost:8650"
PROXY_V1 = f"{PROXY_URL}/v1"


def _check_proxy() -> bool:
    """Return True if the AgentLens proxy is reachable."""
    try:
        response = httpx.get(f"{PROXY_URL}/health", timeout=3.0)
        return response.status_code == 200
    except httpx.ConnectError:
        return False


def _run_crew() -> None:
    """Configure and run a three-agent CrewAI crew pointed at the AgentLens proxy."""
    # Import here so the module is usable even without crewai installed.
    from crewai import LLM, Agent, Crew, Task

    proxy_llm = LLM(
        model="openai/gpt-4o-mini",
        base_url=PROXY_V1,
        api_key="agentlens-mock",
        temperature=0.1,
        timeout=60.0,
    )

    scientist = Agent(
        role="ML Scientist",
        goal="Propose data-driven improvements to molecular property prediction models",
        backstory=(
            "You are a senior ML scientist specializing in cheminformatics and molecular property prediction. "
            "You understand Morgan fingerprints, physicochemical descriptors, MACCS keys, and ensemble methods. "
            "You always justify proposals with scientific reasoning."
        ),
        llm=proxy_llm,
        max_iter=3,
        allow_delegation=False,
        verbose=True,
    )

    engineer = Agent(
        role="ML Engineer",
        goal="Design implementation plans for ML experiments",
        backstory=(
            "You are an ML engineer who translates scientific proposals into concrete implementation steps. "
            "You specify exact libraries (RDKit, scikit-learn), function calls, and parameter choices. "
            "You flag potential issues like feature dimensionality or overfitting risk."
        ),
        llm=proxy_llm,
        max_iter=3,
        allow_delegation=False,
        verbose=True,
    )

    evaluator = Agent(
        role="Experiment Evaluator",
        goal="Assess ML experiment proposals for feasibility and expected impact",
        backstory=(
            "You are a senior reviewer who evaluates ML experiment proposals. You check for scientific "
            "validity, implementation feasibility, and expected ROI. You score proposals on a 1-5 scale "
            "and flag risks."
        ),
        llm=proxy_llm,
        max_iter=3,
        allow_delegation=False,
        verbose=True,
    )

    hypothesis_task = Task(
        description=(
            "The current BBBP (blood-brain barrier penetration) prediction model uses Morgan fingerprints "
            "(1024 bits, radius 2) with LogisticRegression, achieving ROC-AUC of 0.8951 on ~2050 molecules. "
            "Propose ONE specific improvement to the feature engineering or model architecture that could "
            "improve performance. Be specific about what features to add or what model to use. Justify your "
            "proposal with scientific reasoning."
        ),
        expected_output=(
            "A specific proposal with: (1) what to change, "
            "(2) why it should improve performance, (3) expected magnitude of improvement"
        ),
        agent=scientist,
    )

    implementation_task = Task(
        description=(
            "Based on the ML Scientist's proposal, write a concrete implementation plan. Specify: exact Python "
            "code changes needed, libraries to import (e.g., RDKit descriptors, sklearn models), any "
            "hyperparameters, and potential pitfalls to watch for."
        ),
        expected_output="A step-by-step implementation plan with specific code changes, library calls, and parameters",
        agent=engineer,
        context=[hypothesis_task],
    )

    evaluation_task = Task(
        description=(
            "Review the ML Scientist's proposal and the ML Engineer's implementation plan. Assess: "
            "(1) scientific validity of the hypothesis, (2) feasibility of implementation, "
            "(3) risk of overfitting or data leakage, (4) expected improvement range. "
            "Give a score from 1-5 and a go/no-go recommendation."
        ),
        expected_output=(
            "An assessment with scores for validity, feasibility, risk, and a final go/no-go recommendation"
        ),
        agent=evaluator,
        context=[hypothesis_task, implementation_task],
    )

    crew = Crew(
        agents=[scientist, engineer, evaluator],
        tasks=[hypothesis_task, implementation_task, evaluation_task],
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


def _evaluate_traces(*, html: bool = False, output: str = "report.html") -> None:
    """Finalise the trace, fetch it, and run AgentLens evaluators."""
    from pathlib import Path

    from agentlens.engine import EvaluationSuite
    from agentlens.models.expectation import TaskExpectation
    from agentlens.models.trace import Trace
    from agentlens.report.terminal import print_report

    # Finalize: flush in-flight spans into a completed Trace object.
    httpx.post(f"{PROXY_URL}/traces/reset")

    response = httpx.get(f"{PROXY_URL}/traces")
    response.raise_for_status()
    traces_data: list[dict] = response.json()  # type: ignore[type-arg]

    if not traces_data:
        print("[AgentLens] No traces captured — did the proxy receive any LLM calls?")
        return

    suite = EvaluationSuite()
    expected = TaskExpectation(
        expected_output="ROC-AUC",
        forbidden_tools=["send_email", "delete_file", "execute_code"],
        max_steps=10,
        policies=["neural network", "deep learning"],
        expected_escalation=False,
    )

    for trace_data in traces_data:
        trace = Trace.model_validate(trace_data)
        summary = suite.evaluate(trace, expected)
        print_report(summary, trace, verbose=True)

        if html:
            from agentlens.report.html import generate_html_report

            out_path = Path(output)
            generate_html_report(summary, trace, out_path)
            print(f"\nHTML report written to {out_path}")


def _parse_args() -> tuple[bool, str]:
    """Parse --html and -o arguments."""
    import argparse

    parser = argparse.ArgumentParser(description="AgentLens pharma pipeline demo")
    parser.add_argument("--html", action="store_true", help="Generate HTML report")
    parser.add_argument("-o", "--output", default="report.html", help="HTML output path")
    args = parser.parse_args()
    return args.html, args.output


def main() -> None:
    html, output = _parse_args()

    if not _check_proxy():
        print(
            "[AgentLens] ERROR: Proxy is not running.\n"
            "Start it first with:\n\n"
            "    uv run agentlens serve --mode mock --scenario pharma_pipeline\n"
        )
        sys.exit(1)

    print("[AgentLens] Proxy is up. Running CrewAI pharma pipeline...\n")
    _run_crew()

    print("\n[AgentLens] Evaluating captured traces...\n")
    _evaluate_traces(html=html, output=output)


if __name__ == "__main__":
    main()
