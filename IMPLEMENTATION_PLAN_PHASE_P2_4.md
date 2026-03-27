# Phase P2.4: Benchmark Suite (Minimal Viable)

**Dependencies:** None
**Agent:** `python-fastapi`

## Overview

Add a `benchmark` CLI command that runs evaluation over a suite of trace files and produces an aggregate report. This is the minimal version — run a suite, get aggregate scores. No comparison (that's P3.2).

## Design

A benchmark suite is a JSON file listing traces + expectations:

```json
{
  "name": "Agent Quality v1",
  "description": "Baseline quality gate for research agent",
  "cases": [
    {
      "trace": "demo/fixtures/happy_path.json",
      "expectations": {
        "expected_output": "trillion",
        "expected_tools": ["search", "calculator", "cite_source"],
        "forbidden_tools": ["send_email"],
        "max_steps": 8
      }
    },
    {
      "trace": "demo/fixtures/loop_scenario.json",
      "expectations": {
        "expected_output": "GDP",
        "max_steps": 5
      }
    },
    {
      "trace": "demo/fixtures/risk_scenario.json",
      "expectations": {
        "expected_output": "trillion",
        "forbidden_tools": ["send_email"],
        "max_steps": 6
      }
    }
  ]
}
```

## Files to Create

### `src/agentlens/benchmark.py` (CREATE)
**Purpose:** Load and run benchmark suites
**Classes/Functions:**

#### `BenchmarkCase(BaseModel, frozen=True)`
- `trace: str` — path to trace JSON (relative to suite file or absolute)
- `expectations: TaskExpectation | None = None`

#### `BenchmarkSuite(BaseModel, frozen=True)`
- `name: str`
- `description: str = ""`
- `cases: list[BenchmarkCase]`

#### `BenchmarkResult(BaseModel)`
- `suite_name: str`
- `total_cases: int`
- `passed: int` — cases where overall_score >= 0.7
- `failed: int` — cases where overall_score < 0.7
- `average_score: float`
- `level_averages: dict[EvalLevel, float]`
- `case_results: list[EvalSummary]`
- Property `pass_rate` -> float (passed / total_cases)

#### `run_benchmark(suite_path: Path) -> BenchmarkResult`
1. Load suite JSON: `BenchmarkSuite.model_validate_json(suite_path.read_text())`
2. Resolve trace paths relative to suite file location
3. For each case:
   - Load trace: `Trace.model_validate_json(trace_path.read_text())`
   - Load expectations from the case (already parsed as TaskExpectation via Pydantic)
   - Run `EvaluationSuite().evaluate(trace, expectations)`
4. Aggregate: count passed/failed, compute average scores per level
5. Return `BenchmarkResult`

**Constraints:**
- Under 100 lines
- No new dependencies
- Uses existing `EvaluationSuite` and `TaskExpectation`
- Trace paths resolved relative to **CWD** (current working directory), NOT relative to suite file location. This means `"trace": "demo/fixtures/happy_path.json"` works when running from project root. This is the simplest approach and matches how CLI users think.
- Pydantic automatically coerces the `expectations` dict from JSON into `TaskExpectation`. No custom parsing needed — just declare the field as `TaskExpectation | None`.

### `benchmarks/default.json` (CREATE)
**Purpose:** Default benchmark suite using the 3 existing demo fixtures
Content as shown in the Design section above. Paths relative to project root.

## Files to Modify

### `src/agentlens/cli.py` (MODIFY)
**Changes:**
Add `benchmark` command:
```python
@app.command()
def benchmark(
    suite_file: Annotated[Path, typer.Argument(help="Path to benchmark suite JSON")],
    html: Annotated[bool, typer.Option("--html", help="Generate HTML report per case")] = False,
    output_dir: Annotated[Path, typer.Option("--output-dir", "-o", help="Output directory for reports")] = Path("benchmark_results"),
) -> None:
    """Run a benchmark suite and show aggregate results."""
    from agentlens.benchmark import run_benchmark

    result = run_benchmark(suite_file)

    typer.echo(f"\nBenchmark: {result.suite_name}")
    typer.echo(f"Cases: {result.total_cases} | Passed: {result.passed} | Failed: {result.failed}")
    typer.echo(f"Pass rate: {result.pass_rate:.0%}")
    typer.echo(f"Average score: {result.average_score:.0%}")
    typer.echo()
    for level, score in result.level_averages.items():
        typer.echo(f"  {level.value.capitalize():15s} {score:.0%}")
```

If `--html`, generate individual HTML reports per case into `output_dir/`.

### `src/agentlens/__init__.py` (MODIFY)
**Changes:** Export `run_benchmark` and `BenchmarkResult` from public API.

## Test File

### `tests/test_benchmark.py` (CREATE)
**Tests:**
- `test_run_benchmark_loads_and_evaluates_all_cases` — Run on `benchmarks/default.json`, verify total_cases == 3, all case_results present
- `test_run_benchmark_calculates_pass_rate` — Verify passed + failed == total_cases
- `test_run_benchmark_average_score_in_range` — Average score between 0.0 and 1.0
- `test_run_benchmark_level_averages_has_all_levels` — All 4 EvalLevel keys present
- `test_benchmark_case_with_no_expectations` — Case with null expectations still evaluates (uses defaults)
- `test_benchmark_missing_trace_raises` — Non-existent trace path raises FileNotFoundError

**Fixture strategy:** Use the existing `benchmarks/default.json` file for integration-style tests. For unit tests, create a temp suite JSON in `tmp_path` pointing to the existing demo fixtures.

## Verification

```bash
uv run pytest tests/test_benchmark.py -v
uv run agentlens benchmark benchmarks/default.json
# Expected output:
# Benchmark: Agent Quality v1
# Cases: 3 | Passed: 2 | Failed: 1
# Pass rate: 67%
# Average score: 89%
#   Business         97%
#   Behavior         88%
#   Risk             89%
#   Operational      88%
```
