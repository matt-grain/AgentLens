"""Tests for benchmark suite loading and evaluation aggregation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentlens.benchmark import BenchmarkResult, BenchmarkSuite, run_benchmark
from agentlens.models.evaluation import EvalLevel

# Path to default suite — tests must be run from project root
_DEFAULT_SUITE = Path("benchmarks/default.json")


def test_run_benchmark_loads_and_evaluates_all_cases() -> None:
    # Arrange / Act
    result = run_benchmark(_DEFAULT_SUITE)

    # Assert
    assert result.total_cases == 3
    assert len(result.case_results) == 3


def test_run_benchmark_calculates_pass_rate() -> None:
    # Arrange / Act
    result = run_benchmark(_DEFAULT_SUITE)

    # Assert
    assert result.passed + result.failed == result.total_cases
    assert result.pass_rate == result.passed / result.total_cases


def test_run_benchmark_average_score_in_range() -> None:
    # Arrange / Act
    result = run_benchmark(_DEFAULT_SUITE)

    # Assert
    assert 0.0 <= result.average_score <= 1.0


def test_run_benchmark_level_averages_has_all_levels() -> None:
    # Arrange / Act
    result = run_benchmark(_DEFAULT_SUITE)

    # Assert — all four EvalLevel keys must be present
    for level in EvalLevel:
        assert level in result.level_averages, f"Missing level: {level}"
        assert 0.0 <= result.level_averages[level] <= 1.0


def test_benchmark_case_with_no_expectations(tmp_path: Path) -> None:
    # Arrange — suite with one case and null expectations
    suite_data = {
        "name": "No-expectations suite",
        "cases": [{"trace": "demo/fixtures/happy_path.json", "expectations": None}],
    }
    suite_file = tmp_path / "suite.json"
    suite_file.write_text(json.dumps(suite_data))

    # Act
    result = run_benchmark(suite_file)

    # Assert — evaluation still completes with default evaluators
    assert result.total_cases == 1
    assert len(result.case_results) == 1
    assert 0.0 <= result.average_score <= 1.0


def test_benchmark_missing_trace_raises(tmp_path: Path) -> None:
    # Arrange — suite pointing to a non-existent trace
    suite_data = {
        "name": "Bad suite",
        "cases": [{"trace": "does/not/exist.json"}],
    }
    suite_file = tmp_path / "suite.json"
    suite_file.write_text(json.dumps(suite_data))

    # Act & Assert
    with pytest.raises(FileNotFoundError):
        run_benchmark(suite_file)


def test_benchmark_suite_parses_expectations_from_dict() -> None:
    # Arrange — verify Pydantic coerces expectations dict into TaskExpectation
    suite_data = {
        "name": "Coercion check",
        "cases": [
            {
                "trace": "demo/fixtures/happy_path.json",
                "expectations": {"expected_output": "trillion", "max_steps": 8},
            }
        ],
    }

    # Act
    suite = BenchmarkSuite.model_validate(suite_data)

    # Assert
    assert suite.cases[0].expectations is not None
    assert suite.cases[0].expectations.expected_output == "trillion"
    assert suite.cases[0].expectations.max_steps == 8


def test_benchmark_result_pass_rate_zero_when_no_cases() -> None:
    # Arrange
    result = BenchmarkResult(
        suite_name="empty",
        total_cases=0,
        passed=0,
        failed=0,
        average_score=0.0,
        level_averages={},
        case_results=[],
    )

    # Assert
    assert result.pass_rate == 0.0
