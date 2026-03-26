"""Tests for the AgentLens CLI commands."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from agentlens.cli import app

_runner = CliRunner()


def test_demo_command_runs_all_scenarios() -> None:
    result = _runner.invoke(app, ["demo"])
    assert result.exit_code == 0, result.output
    assert "happy_path" in result.output
    assert "loop" in result.output
    assert "risk" in result.output


def test_demo_command_single_scenario() -> None:
    result = _runner.invoke(app, ["demo", "--scenario", "happy_path"])
    assert result.exit_code == 0, result.output
    assert "happy_path" in result.output


def test_demo_command_unknown_scenario_exits_with_error() -> None:
    result = _runner.invoke(app, ["demo", "--scenario", "nonexistent"])
    assert result.exit_code != 0


def test_demo_command_html_output(tmp_path: Path) -> None:
    out = tmp_path / "test_report.html"
    result = _runner.invoke(app, ["demo", "--scenario", "happy_path", "--html", "--output", str(out)])
    assert result.exit_code == 0, result.output
    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert "<html" in content


def test_demo_command_verbose_shows_evaluators() -> None:
    result = _runner.invoke(app, ["demo", "--scenario", "happy_path", "--verbose"])
    assert result.exit_code == 0, result.output


def test_evaluate_command_with_trace_file(tmp_path: Path) -> None:
    fixtures = Path(__file__).parent.parent / "demo" / "fixtures" / "happy_path.json"
    result = _runner.invoke(app, ["evaluate", str(fixtures)])
    assert result.exit_code == 0, result.output


def test_evaluate_command_missing_file_exits_with_error(tmp_path: Path) -> None:
    result = _runner.invoke(app, ["evaluate", str(tmp_path / "missing.json")])
    assert result.exit_code != 0


def test_evaluate_command_html_output(tmp_path: Path) -> None:
    fixtures = Path(__file__).parent.parent / "demo" / "fixtures" / "happy_path.json"
    out = tmp_path / "eval_report.html"
    result = _runner.invoke(app, ["evaluate", str(fixtures), "--html", "--output", str(out)])
    assert result.exit_code == 0, result.output
    assert out.exists()


def test_serve_command_help_text() -> None:
    """Verify serve command is registered and has expected options."""
    result = _runner.invoke(app, ["serve", "--help"])
    assert result.exit_code == 0
    assert "--mode" in result.output
    assert "--port" in result.output


def test_app_help_lists_all_commands() -> None:
    result = _runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "demo" in result.output
    assert "evaluate" in result.output
    assert "serve" in result.output
