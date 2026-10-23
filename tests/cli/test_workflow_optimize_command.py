"""Tests for benchmark checks made by `workflow optimize` before runtime bootstrap."""

from pathlib import Path
from uuid import UUID

import pytest

import azathoth.cli.workflows as workflow_commands
from azathoth.cli import CliRuntimeConfiguration
from azathoth.evaluation import (
    BenchmarkCase,
    BenchmarkDataset,
    ExpectedOutcome,
    OutcomeComparison,
    SQLiteBenchmarkRepository,
)
from azathoth.workflows import SQLiteWorkflowRepository
from tests.cli.test_optimization_lifecycle import (
    WORKFLOW_ID,
    create_workflow,
)

BENCHMARK_ID = UUID("b1b1b1b1-b1b1-4b1b-8b1b-b1b1b1b1b1b1")

FIRST_CASE_ID = UUID("c1c1c1c1-c1c1-4c1c-8c1c-c1c1c1c1c1c1")

SEMANTIC_CASE_ID = UUID("c2c2c2c2-c2c2-4c2c-8c2c-c2c2c2c2c2c2")


def configure(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> CliRuntimeConfiguration:
    """Point the CLI at an isolated database and forbid runtime bootstrap."""

    configuration = CliRuntimeConfiguration(
        database=tmp_path / "azathoth.db",
    )

    monkeypatch.setattr(
        CliRuntimeConfiguration,
        "from_environment",
        lambda: configuration,
    )

    def fail_bootstrap(
        _configuration: CliRuntimeConfiguration,
    ) -> object:
        raise AssertionError("Runtime must not be loaded.")

    monkeypatch.setattr(
        workflow_commands,
        "load_runtime",
        fail_bootstrap,
    )

    return configuration


def create_case(
    *,
    case_id: UUID,
    comparison: OutcomeComparison = OutcomeComparison.EXACT,
) -> BenchmarkCase:
    """Create one benchmark case expecting success."""

    return BenchmarkCase(
        id=case_id,
        input="request",
        expected=ExpectedOutcome(
            description="Workflow returns success.",
            value="success",
            comparison=comparison,
        ),
    )


def save_benchmark(
    configuration: CliRuntimeConfiguration,
    *cases: BenchmarkCase,
) -> None:
    """Persist one benchmark with the given cases."""

    SQLiteBenchmarkRepository(configuration.database).save(
        BenchmarkDataset(
            id=BENCHMARK_ID,
            name="optimize-checks",
            description="Benchmark used for optimize command checks.",
            cases=cases,
        )
    )


def optimize() -> int:
    """Run the optimize command against the test workflow and benchmark."""

    return workflow_commands.optimize_workflow(
        workflow_id=WORKFLOW_ID,
        benchmark_id=BENCHMARK_ID,
        target_latency_seconds=60.0,
        target_cost_usd=0.01,
        generations=1,
    )


def test_optimize_rejects_unconfigured_benchmark_before_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    assert optimize() == 1

    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == f"Benchmark dataset {BENCHMARK_ID} is not configured.\n"


def test_optimize_rejects_empty_benchmark_before_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configuration = configure(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    save_benchmark(configuration)

    assert optimize() == 1

    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == f"Benchmark {BENCHMARK_ID} has no cases.\n"


def test_optimize_rejects_unsupported_comparison_before_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configuration = configure(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    save_benchmark(
        configuration,
        create_case(
            case_id=FIRST_CASE_ID,
        ),
        create_case(
            case_id=SEMANTIC_CASE_ID,
            comparison=OutcomeComparison.SEMANTIC,
        ),
    )

    assert optimize() == 1

    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == (
        f"Benchmark case {SEMANTIC_CASE_ID} uses comparison 'semantic', "
        "which is not supported yet.\n"
    )


def test_optimize_rejects_workflow_without_result_before_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configuration = configure(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    save_benchmark(
        configuration,
        create_case(
            case_id=FIRST_CASE_ID,
        ),
    )

    SQLiteWorkflowRepository(configuration.database).save(
        create_workflow().model_copy(
            update={
                "result": None,
            }
        )
    )

    assert optimize() == 1

    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == f"Workflow {WORKFLOW_ID} does not declare a result.\n"
