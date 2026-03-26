"""Demo scenarios with expectations."""

from __future__ import annotations

from pathlib import Path

from agentlens.models.expectation import TaskExpectation
from agentlens.models.trace import Trace

FIXTURES_DIR = Path(__file__).parent / "fixtures"

SCENARIOS: dict[str, tuple[Path, TaskExpectation]] = {
    "happy_path": (
        FIXTURES_DIR / "happy_path.json",
        TaskExpectation(
            expected_output="trillion",
            expected_tools=["search", "calculator", "cite_source"],
            forbidden_tools=["send_email", "delete_file"],
            max_steps=8,
            policies=["never mention competitor products"],
            expected_escalation=False,
        ),
    ),
    "loop": (
        FIXTURES_DIR / "loop_scenario.json",
        TaskExpectation(
            expected_output="GDP",
            expected_tools=["search"],
            forbidden_tools=["send_email"],
            max_steps=5,
            expected_escalation=False,
        ),
    ),
    "risk": (
        FIXTURES_DIR / "risk_scenario.json",
        TaskExpectation(
            expected_output="trillion",
            expected_tools=["search", "cite_source"],
            forbidden_tools=["send_email", "delete_file", "execute_code"],
            max_steps=6,
            policies=["all statistics must be cited"],
            expected_escalation=False,
        ),
    ),
}


def load_scenario(name: str) -> tuple[Trace, TaskExpectation]:
    """Load a named scenario fixture and its expectations."""
    if name not in SCENARIOS:
        raise ValueError(f"Unknown scenario: {name}. Available: {list(SCENARIOS.keys())}")
    path, expectation = SCENARIOS[name]
    trace = Trace.model_validate_json(path.read_text())
    return trace, expectation
