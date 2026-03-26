"""Rich terminal report for evaluation results."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table
from rich.text import Text

from agentlens.models.evaluation import EvalLevel, EvalResult, EvalSummary
from agentlens.models.trace import Span, SpanStatus, Trace

_LEVEL_ORDER: list[EvalLevel] = [
    EvalLevel.BUSINESS,
    EvalLevel.BEHAVIOR,
    EvalLevel.RISK,
    EvalLevel.OPERATIONAL,
]


def print_report(
    summary: EvalSummary,
    trace: Trace,
    verbose: bool = False,
    console: Console | None = None,
) -> None:
    """Print a formatted evaluation report to the terminal."""
    con = console if console is not None else Console()
    _print_header(con, summary, trace)
    _print_level_scores(con, summary)
    _print_trajectory(con, trace)
    if verbose:
        _print_detailed_results(con, summary)


def _print_header(console: Console, summary: EvalSummary, trace: Trace) -> None:
    total_ms = trace.duration_ms
    tokens = trace.total_tokens
    token_str = f"{tokens.input_tokens}in / {tokens.output_tokens}out" if tokens else "n/a"
    overall_color = _score_color(summary.overall_score)

    console.rule("[bold]AgentLens Evaluation Report[/bold]")
    console.print(f"[bold]Task:[/bold] {summary.task}")
    console.print(f"[bold]Agent:[/bold] {trace.agent_name}  |  [bold]Trace:[/bold] {trace.id}")
    steps = len(trace.spans)
    console.print(f"[bold]Duration:[/bold] {total_ms}ms  |  [bold]Steps:[/bold] {steps}")
    console.print(f"[bold]Tokens:[/bold] {token_str}")
    console.print(f"[bold]Overall Score:[/bold] [{overall_color}]{summary.overall_score:.0%}[/{overall_color}]")
    console.print()


def _print_level_scores(console: Console, summary: EvalSummary) -> None:
    table = Table(title="Level Scores", show_header=True, header_style="bold")
    table.add_column("Level", style="bold")
    table.add_column("Score", justify="right")
    table.add_column("Status", justify="center")

    for level in _LEVEL_ORDER:
        score = summary.level_scores.get(level)
        if score is None:
            continue
        color = _score_color(score)
        status = "PASS" if score >= 0.5 else "FAIL"
        table.add_row(level.value.capitalize(), f"[{color}]{score:.0%}[/{color}]", f"[{color}]{status}[/{color}]")

    console.print(table)
    console.print()


def _print_trajectory(console: Console, trace: Trace) -> None:
    console.print("[bold]Trajectory Timeline[/bold]")
    for span in trace.spans:
        icon = _span_icon(span)
        duration = span.duration_ms
        console.print(f"  {icon} [{span.span_type}] [bold]{span.name}[/bold]  ({duration}ms)")
    console.print()


def _print_detailed_results(console: Console, summary: EvalSummary) -> None:
    console.print("[bold]Detailed Evaluator Results[/bold]")
    for result in summary.results:
        _print_result(console, result)


def _print_result(console: Console, result: EvalResult) -> None:
    color = _score_color(result.score)
    status = "[green]PASS[/green]" if result.passed else "[red]FAIL[/red]"
    console.print(f"  [{color}]{result.evaluator_name}[/{color}] ({result.level.value}) — {status} {result.score:.0%}")
    console.print(f"    {result.message}")
    for ev in result.evidence:
        console.print(f"    • {ev}")


def _score_color(score: float) -> str:
    if score >= 0.8:
        return "green"
    if score >= 0.5:
        return "yellow"
    return "red"


def _span_icon(span: Span) -> Text:
    if span.status == SpanStatus.FAILURE:
        return Text("✗", style="red")
    if span.status == SpanStatus.TIMEOUT:
        return Text("⚠", style="yellow")
    return Text("✓", style="green")
