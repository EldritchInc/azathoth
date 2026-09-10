"""Tests for executing durable benchmarks through the CLI command layer."""

from pathlib import Path
from uuid import UUID

import pytest

import azathoth.cli.benchmarks as benchmark_commands
from azathoth.cli import (
    DATABASE_ENVIRONMENT_VARIABLE,
    run_benchmark,
)
from azathoth.evaluation import (
    BenchmarkCase,
    BenchmarkDataset,
    ExpectedOutcome,
    OutcomeComparison,
    SQLiteBenchmarkRepository,
)
from azathoth.runtime import WorkflowNotConfiguredError
from azathoth.workflows import (
    WorkflowBenchmarkResult,
    WorkflowGenerationError,
)

BENCHMARK_ID = UUID("11111111-1111-1111-1111-111111111111")

UNKNOWN_BENCHMARK_ID = UUID("99999999-9999-9999-9999-999999999999")

WORKFLOW_ID = UUID("22222222-2222-2222-2222-222222222222")

CASE_ID = UUID("33333333-3333-3333-3333-333333333333")


def create_dataset() -> BenchmarkDataset:
    """Create one deterministic durable benchmark."""

    return BenchmarkDataset(
        id=BENCHMARK_ID,
        name="classification",
        description="Verify deterministic classification.",
        version="1.0.0",
        cases=(
            BenchmarkCase(
                id=CASE_ID,
                input="hello",
                expected=ExpectedOutcome(
                    description="Return positive.",
                    value="positive",
                    comparison=OutcomeComparison.EXACT,
                ),
            ),
        ),
    )


def configure_database(
    *,
    database: Path,
    monkeypatch: pytest.MonkeyPatch,
    persist_dataset: bool = True,
) -> None:
    """Configure one isolated benchmark CLI database."""

    monkeypatch.setenv(
        DATABASE_ENVIRONMENT_VARIABLE,
        str(database),
    )

    if persist_dataset:
        SQLiteBenchmarkRepository(
            database,
        ).save(
            create_dataset(),
        )


def test_benchmark_run_executes_persisted_dataset(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    configure_database(
        database=database,
        monkeypatch=monkeypatch,
    )

    runtime = object()

    monkeypatch.setattr(
        benchmark_commands,
        "load_runtime",
        lambda _configuration: runtime,
    )

    calls: list[
        tuple[
            object,
            UUID,
            BenchmarkDataset,
            str,
        ]
    ] = []

    result = WorkflowBenchmarkResult(
        dataset_id=BENCHMARK_ID,
    )

    async def fake_execute_configured_benchmark(
        *,
        runtime: object,
        workflow_id: UUID,
        dataset: BenchmarkDataset,
        output_name: str,
    ) -> WorkflowBenchmarkResult:
        calls.append(
            (
                runtime,
                workflow_id,
                dataset,
                output_name,
            )
        )

        return result

    monkeypatch.setattr(
        benchmark_commands,
        "execute_configured_benchmark",
        fake_execute_configured_benchmark,
    )

    monkeypatch.setattr(
        benchmark_commands,
        "render_workflow_benchmark_result",
        lambda result, *, workflow_id: f"rendered {result.dataset_id} {workflow_id}",
    )

    status = run_benchmark(
        benchmark_id=BENCHMARK_ID,
        workflow_id=WORKFLOW_ID,
        output_name="classification",
    )

    captured = capsys.readouterr()

    assert status == 0

    assert calls == [
        (
            runtime,
            WORKFLOW_ID,
            create_dataset(),
            "classification",
        )
    ]

    assert captured.out == (f"rendered {BENCHMARK_ID} {WORKFLOW_ID}\n")

    assert captured.err == ""


def test_benchmark_run_rejects_unknown_dataset_before_runtime_bootstrap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    configure_database(
        database=database,
        monkeypatch=monkeypatch,
        persist_dataset=False,
    )

    def fail_load_runtime(
        _configuration: object,
    ) -> object:
        raise AssertionError("runtime must not bootstrap for an unknown benchmark")

    monkeypatch.setattr(
        benchmark_commands,
        "load_runtime",
        fail_load_runtime,
    )

    status = run_benchmark(
        benchmark_id=UNKNOWN_BENCHMARK_ID,
        workflow_id=WORKFLOW_ID,
        output_name="classification",
    )

    captured = capsys.readouterr()

    assert status == 1
    assert captured.out == ""

    assert captured.err == (f"Benchmark dataset {UNKNOWN_BENCHMARK_ID} is not configured.\n")


@pytest.mark.parametrize(
    ("error", "message"),
    (
        (
            WorkflowNotConfiguredError("Configured workflow is unavailable."),
            "Configured workflow is unavailable.",
        ),
        (
            WorkflowGenerationError("Configured workflow cannot become executable."),
            "Configured workflow cannot become executable.",
        ),
    ),
)
def test_benchmark_run_reports_workflow_execution_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    error: Exception,
    message: str,
) -> None:
    database = tmp_path / "azathoth.db"

    configure_database(
        database=database,
        monkeypatch=monkeypatch,
    )

    monkeypatch.setattr(
        benchmark_commands,
        "load_runtime",
        lambda _configuration: object(),
    )

    async def fail_execute_configured_benchmark(
        **_kwargs: object,
    ) -> WorkflowBenchmarkResult:
        raise error

    monkeypatch.setattr(
        benchmark_commands,
        "execute_configured_benchmark",
        fail_execute_configured_benchmark,
    )

    status = run_benchmark(
        benchmark_id=BENCHMARK_ID,
        workflow_id=WORKFLOW_ID,
        output_name="classification",
    )

    captured = capsys.readouterr()

    assert status == 1
    assert captured.out == ""
    assert captured.err == f"{message}\n"
