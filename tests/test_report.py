"""Tests for terminal and HTML report generators."""

from __future__ import annotations

from io import StringIO
from pathlib import Path

from rich.console import Console

from agentlens.models.evaluation import EvalSummary
from agentlens.models.trace import Trace
from agentlens.report.html import render_html_report
from agentlens.report.terminal import print_report


def _capture_report(summary: EvalSummary, trace: Trace, verbose: bool = False) -> str:
    """Render the terminal report to a string buffer via injected console."""
    buf = StringIO()
    console = Console(file=buf, no_color=True, highlight=False)
    print_report(summary, trace, verbose=verbose, console=console)
    return buf.getvalue()


def test_print_report_outputs_task(sample_eval_summary: EvalSummary, sample_trace: Trace) -> None:
    output = _capture_report(sample_eval_summary, sample_trace)
    assert "Research task" in output


def test_print_report_shows_level_scores(sample_eval_summary: EvalSummary, sample_trace: Trace) -> None:
    output = _capture_report(sample_eval_summary, sample_trace)
    assert "behavior" in output.lower() or "risk" in output.lower()


def test_print_report_verbose_shows_evaluator_names(sample_eval_summary: EvalSummary, sample_trace: Trace) -> None:
    output = _capture_report(sample_eval_summary, sample_trace, verbose=True)
    assert "tool_use" in output
    assert "policy_check" in output


def test_print_report_trajectory_shows_span_names(sample_eval_summary: EvalSummary, sample_trace: Trace) -> None:
    output = _capture_report(sample_eval_summary, sample_trace)
    assert "plan" in output
    assert "search" in output
    assert "synthesize" in output


def test_print_report_shows_overall_score(sample_eval_summary: EvalSummary, sample_trace: Trace) -> None:
    output = _capture_report(sample_eval_summary, sample_trace)
    assert "50%" in output


def test_generate_html_report_creates_file(
    sample_eval_summary: EvalSummary, sample_trace: Trace, tmp_path: Path
) -> None:
    from agentlens.report.html import generate_html_report

    out = tmp_path / "report.html"
    generate_html_report(sample_eval_summary, sample_trace, out)

    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert len(content) > 100


def test_html_report_contains_scores(sample_eval_summary: EvalSummary, sample_trace: Trace) -> None:
    html = render_html_report(sample_eval_summary, sample_trace)

    assert "50%" in html
    assert "100%" in html
    assert "0%" in html


def test_html_report_contains_trajectory(sample_eval_summary: EvalSummary, sample_trace: Trace) -> None:
    html = render_html_report(sample_eval_summary, sample_trace)

    for span in sample_trace.spans:
        assert span.name in html


def test_html_report_contains_agent_name(sample_eval_summary: EvalSummary, sample_trace: Trace) -> None:
    html = render_html_report(sample_eval_summary, sample_trace)
    assert sample_trace.agent_name in html


def test_html_report_contains_evaluator_results(sample_eval_summary: EvalSummary, sample_trace: Trace) -> None:
    html = render_html_report(sample_eval_summary, sample_trace)
    assert "tool_use" in html
    assert "policy_check" in html
