"""AgentLens CLI entry point."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer

app = typer.Typer(help="AgentLens — Trajectory-first agent evaluation")

# Project root is three levels up: src/agentlens/cli.py -> src/agentlens -> src -> project root
_PROJECT_ROOT = Path(__file__).parent.parent.parent


def _ensure_demo_importable() -> None:
    """Add project root to sys.path so the demo package is importable."""
    root = str(_PROJECT_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


@app.command()
def demo(
    scenario: Annotated[
        str,
        typer.Option("--scenario", "-s", help="Scenario to run: happy_path|loop|risk|all"),
    ] = "all",
    live: Annotated[bool, typer.Option("--live", help="Use live agent (not yet available)")] = False,
    proxy_to: Annotated[str | None, typer.Option("--proxy-to", help="Proxy target URL")] = None,
    html: Annotated[bool, typer.Option("--html", help="Also generate an HTML report")] = False,
    output: Annotated[Path, typer.Option("--output", "-o", help="HTML output path")] = Path("report.html"),
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Show per-evaluator detail")] = False,
) -> None:
    """Run demo scenario(s) and print evaluation reports."""
    if live:
        typer.echo("Live mode not yet available.")
        raise typer.Exit(1)

    _ensure_demo_importable()

    from agentlens.engine import EvaluationSuite
    from agentlens.report import generate_html_report, print_report
    from demo.scenarios import SCENARIOS, load_scenario  # type: ignore[import-untyped]  # demo/ is unpackaged

    names = list(SCENARIOS.keys()) if scenario == "all" else [scenario]
    suite = EvaluationSuite()

    for name in names:
        typer.echo(f"\n=== Scenario: {name} ===")
        trace, expectation = load_scenario(name)
        summary = suite.evaluate(trace, expectation)
        print_report(summary, trace, verbose=verbose)

        if html:
            out = output if len(names) == 1 else output.with_stem(f"{output.stem}_{name}")
            generate_html_report(summary, trace, out)
            typer.echo(f"HTML report written to {out}")


@app.command()
def evaluate(
    trace_file: Annotated[Path, typer.Argument(help="Path to trace JSON file")],
    expectations: Annotated[
        Path | None,
        typer.Option("--expectations", "-e", help="Path to TaskExpectation JSON file"),
    ] = None,
    html: Annotated[bool, typer.Option("--html", help="Generate an HTML report")] = False,
    output: Annotated[Path, typer.Option("--output", "-o", help="HTML output path")] = Path("report.html"),
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Show per-evaluator detail")] = False,
) -> None:
    """Evaluate a trace file and print the report."""
    from agentlens.engine import EvaluationSuite
    from agentlens.models.expectation import TaskExpectation
    from agentlens.models.trace import Trace
    from agentlens.report import generate_html_report, print_report

    if not trace_file.exists():
        typer.echo(f"Error: trace file not found: {trace_file}", err=True)
        raise typer.Exit(1)

    trace = Trace.model_validate_json(trace_file.read_text())
    expectation: TaskExpectation | None = None
    if expectations is not None:
        expectation = TaskExpectation.model_validate_json(expectations.read_text())

    suite = EvaluationSuite()
    summary = suite.evaluate(trace, expectation)
    print_report(summary, trace, verbose=verbose)

    if html:
        generate_html_report(summary, trace, output)
        typer.echo(f"HTML report written to {output}")


@app.command("export-otel")
def export_otel(
    trace_file: Annotated[Path, typer.Argument(help="Path to trace JSON file")],
    output: Annotated[Path, typer.Option("--output", "-o", help="Output path")] = Path("trace_otel.json"),
) -> None:
    """Export a trace in OpenTelemetry JSON format."""
    from agentlens.export.otel import export_otel_json_file
    from agentlens.models.trace import Trace

    if not trace_file.exists():
        typer.echo(f"Error: trace file not found: {trace_file}", err=True)
        raise typer.Exit(1)

    trace = Trace.model_validate_json(trace_file.read_text())
    export_otel_json_file(trace, output)
    typer.echo(f"OTel JSON written to {output}")


@app.command()
def benchmark(
    suite_file: Annotated[Path, typer.Argument(help="Path to benchmark suite JSON")],
    html: Annotated[bool, typer.Option("--html", help="Generate HTML report per case")] = False,
    output_dir: Annotated[Path, typer.Option("--output-dir", "-o", help="Output directory for reports")] = Path(
        "benchmark_results"
    ),
) -> None:
    """Run a benchmark suite and show aggregate results."""
    from agentlens.benchmark import run_benchmark
    from agentlens.report import generate_html_report

    if not suite_file.exists():
        typer.echo(f"Error: suite file not found: {suite_file}", err=True)
        raise typer.Exit(1)

    result = run_benchmark(suite_file)

    typer.echo(f"\nBenchmark: {result.suite_name}")
    typer.echo(f"Cases: {result.total_cases} | Passed: {result.passed} | Failed: {result.failed}")
    typer.echo(f"Pass rate: {result.pass_rate:.0%}")
    typer.echo(f"Average score: {result.average_score:.0%}")
    typer.echo()
    for level, score in result.level_averages.items():
        typer.echo(f"  {level.value.capitalize():15s} {score:.0%}")

    if html:
        from agentlens.benchmark import BenchmarkSuite
        from agentlens.models.trace import Trace

        output_dir.mkdir(parents=True, exist_ok=True)
        suite = BenchmarkSuite.model_validate_json(suite_file.read_text())
        for i, (case, summary) in enumerate(zip(suite.cases, result.case_results, strict=True)):
            trace = Trace.model_validate_json(Path(case.trace).read_text())
            out = output_dir / f"case_{i}_{Path(case.trace).stem}.html"
            generate_html_report(summary, trace, out)
        typer.echo(f"HTML reports written to {output_dir}/")


@app.command()
def serve(
    mode: Annotated[str, typer.Option("--mode", "-m", help="Server mode: mock|proxy|mailbox")] = "mock",
    proxy_to: Annotated[str | None, typer.Option("--proxy-to", help="Upstream URL for proxy mode")] = None,
    port: Annotated[int, typer.Option("--port", "-p", help="Port to listen on")] = 8650,
    scenario: Annotated[str, typer.Option("--scenario", "-s", help="Default canned scenario")] = "happy_path",
    timeout: Annotated[float, typer.Option("--timeout", "-t", help="Mailbox request timeout (seconds)")] = 300.0,
    traces_dir: Annotated[
        Path | None,
        typer.Option("--traces-dir", help="Directory to auto-save trace JSON files"),
    ] = Path("traces"),
    session: Annotated[str | None, typer.Option("--session", help="Default session ID for traces")] = None,
    guards: Annotated[Path | None, typer.Option("--guards", help="YAML guard config for real-time evaluation")] = None,
) -> None:
    """Start the AgentLens proxy server."""
    import uvicorn

    from agentlens.server.guards import GuardConfig
    from agentlens.server.models import ServerMode
    from agentlens.server.proxy import create_app

    guards_config: GuardConfig | None = None
    if guards is not None:
        guards_config = GuardConfig.from_yaml(guards)
        typer.echo(f"Guards enabled: {len(guards_config.rules)} rule(s) from {guards}")

    if traces_dir is not None:
        typer.echo(f"Traces will be saved to: {traces_dir.resolve()}")
    fastapi_app = create_app(
        mode=ServerMode(mode),
        proxy_target=proxy_to,
        scenario=scenario,
        timeout=timeout,
        traces_dir=traces_dir,
        session_id=session,
        guards_config=guards_config,
    )
    uvicorn.run(fastapi_app, host="0.0.0.0", port=port)  # noqa: S104  # dev proxy binds all interfaces
