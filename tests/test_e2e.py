"""End-to-end tests covering the full AgentLens pipeline."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from agentlens.engine import EvaluationSuite
from agentlens.models.evaluation import EvalSummary
from agentlens.report import generate_html_report
from agentlens.server.models import ServerMode
from agentlens.server.proxy import create_app

_PROJECT_ROOT = Path(__file__).parent.parent
_FIXTURES_DIR = _PROJECT_ROOT / "demo" / "fixtures"
_HAPPY_PATH_FIXTURE = _FIXTURES_DIR / "happy_path.json"


# ---------------------------------------------------------------------------
# Fixture-based pipeline
# ---------------------------------------------------------------------------


def test_e2e_fixture_demo_all_scenarios_returns_eval_summary() -> None:
    """Load every demo scenario, evaluate, and verify a valid EvalSummary is returned."""
    sys.path.insert(0, str(_PROJECT_ROOT))
    from demo.scenarios import SCENARIOS, load_scenario  # type: ignore[import-untyped]

    suite = EvaluationSuite()
    for name in SCENARIOS:
        trace, expectation = load_scenario(name)
        summary = suite.evaluate(trace, expectation)

        assert isinstance(summary, EvalSummary), f"scenario {name!r} did not return EvalSummary"
        assert summary.trace_id == trace.id
        assert 0.0 <= summary.overall_score <= 1.0
        assert len(summary.results) > 0


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_e2e_cli_demo_command_exits_zero() -> None:
    """uv run agentlens demo must complete without error."""
    result = subprocess.run(
        ["uv", "run", "agentlens", "demo"],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(_PROJECT_ROOT),
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"


@pytest.mark.e2e
def test_e2e_cli_evaluate_command_exits_zero() -> None:
    """uv run agentlens evaluate <fixture> must complete without error."""
    result = subprocess.run(
        ["uv", "run", "agentlens", "evaluate", str(_HAPPY_PATH_FIXTURE)],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(_PROJECT_ROOT),
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"


# ---------------------------------------------------------------------------
# HTML report
# ---------------------------------------------------------------------------


def test_e2e_html_report_generates_valid_html(tmp_path: Path) -> None:
    """Evaluate a fixture and generate an HTML report; verify structure."""
    from agentlens.models.trace import Trace

    trace = Trace.model_validate_json(_HAPPY_PATH_FIXTURE.read_text())
    suite = EvaluationSuite()
    summary = suite.evaluate(trace)

    out = tmp_path / "report.html"
    generate_html_report(summary, trace, out)

    assert out.exists(), "HTML report file was not created"
    content = out.read_text()
    assert "<html" in content.lower(), "output does not look like HTML"
    assert "AgentLens" in content, "report title missing from HTML"
    assert trace.task in content, "task description missing from HTML"


# ---------------------------------------------------------------------------
# Proxy server (mock mode)
# ---------------------------------------------------------------------------


def test_e2e_proxy_mock_mode_captures_trace() -> None:
    """POST chat/completions -> reset -> GET traces verifies a trace was captured."""
    from agentlens.server.canned import REGISTRY

    # Ensure the REGISTRY index is at 0 for happy_path before and after this test
    # so that other tests that share the module-level REGISTRY singleton are unaffected.
    REGISTRY.reset("happy_path")
    try:
        client = TestClient(create_app(mode=ServerMode.MOCK, scenario="happy_path"))

        payload = {
            "model": "agentlens-mock",
            "messages": [{"role": "user", "content": "What is the GDP of France?"}],
        }
        chat_resp = client.post("/v1/chat/completions", json=payload)
        assert chat_resp.status_code == 200

        reset_resp = client.post("/traces/reset")
        assert reset_resp.status_code == 200
        assert reset_resp.json()["status"] == "reset"

        traces_resp = client.get("/traces")
        assert traces_resp.status_code == 200
        traces = traces_resp.json()
        assert len(traces) == 1
        trace = traces[0]
        assert "id" in trace
        assert "spans" in trace
        assert len(trace["spans"]) >= 1
    finally:
        REGISTRY.reset("happy_path")
