"""Tests for comparison reporting in benchmark CLI commands."""

import asyncio
from pathlib import Path
from uuid import UUID

import pytest

import azathoth.cli.benchmarks as benchmark_commands
from azathoth.cli import (
    DATABASE_ENVIRONMENT_VARIABLE,
    compare_benchmarks,
    render_workflow_benchmark_result,
    run_benchmark,
    show_benchmark,
)
from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.evaluation import (
    BenchmarkDataset,
    OutcomeComparison,
    SQLiteBenchmarkRepository,
)
from azathoth.workflows import WorkflowBenchmarkRunner
from tests.workflows.test_benchmark_comparisons import (
    DATASET_ID,
    SEMANTIC_CASE_ID,
    create_candidate,
    create_case,
    create_mixed_dataset,
)

FIRST_WORKFLOW_ID = UUID("77777777-7777-7777-7777-777777777771")

SECOND_WORKFLOW_ID = UUID("77777777-7777-7777-7777-777777777772")


def create_semantic_dataset() -> BenchmarkDataset:
    """Create the mixed benchmark plus one case judged semantically."""

    return create_mixed_dataset().model_copy(
        update={
            "cases": (
                *create_mixed_dataset().cases,
                create_case(
                    SEMANTIC_CASE_ID,
                    OutcomeComparison.SEMANTIC,
                    "The customer asks for a refund.",
                ),
            ),
        }
    )


def persist(
    dataset: BenchmarkDataset,
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Persist one benchmark into an isolated CLI database."""

    database = tmp_path / "azathoth.db"

    SQLiteBenchmarkRepository(database).save(dataset)

    monkeypatch.setenv(
        DATABASE_ENVIRONMENT_VARIABLE,
        str(database),
    )


def forbid_runtime_bootstrap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fail the test if a command bootstraps the provider runtime."""

    def fail_load_runtime(
        configuration: CliRuntimeConfiguration,
    ) -> object:
        raise AssertionError("Runtime must not be bootstrapped.")

    monkeypatch.setattr(
        benchmark_commands,
        "load_runtime",
        fail_load_runtime,
    )


def test_benchmark_show_counts_cases_per_comparison(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    persist(
        create_semantic_dataset(),
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    result = show_benchmark(DATASET_ID)

    captured = capsys.readouterr()

    assert result == 0
    assert "Cases: 4\n" in captured.out
    assert "Comparisons: exact 1, normalized 1, semantic 1, schema 1\n" in captured.out


def test_benchmark_show_reports_no_comparisons_for_empty_benchmark(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    persist(
        create_mixed_dataset().model_copy(update={"cases": ()}),
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    result = show_benchmark(DATASET_ID)

    captured = capsys.readouterr()

    assert result == 0
    assert "Comparisons: none\n" in captured.out


def test_benchmark_result_rendering_breaks_down_passes_by_comparison() -> None:
    result = asyncio.run(
        WorkflowBenchmarkRunner().run(
            create_mixed_dataset(),
            create_candidate,
            output_name="classification",
        )
    )

    rendered = render_workflow_benchmark_result(
        result,
        workflow_id=FIRST_WORKFLOW_ID,
    )

    assert (
        "Accuracy: 0.666667\n"
        "Passed (exact): 0/1\n"
        "Passed (normalized): 1/1\n"
        "Passed (schema): 1/1\n"
        "Total Tokens: "
    ) in rendered


def test_benchmark_run_rejects_unsupported_comparison_before_runtime_bootstrap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    persist(
        create_semantic_dataset(),
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    forbid_runtime_bootstrap(monkeypatch)

    result = run_benchmark(
        benchmark_id=DATASET_ID,
        workflow_id=FIRST_WORKFLOW_ID,
        output_name="classification",
    )

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert captured.err == (
        f"Benchmark case {SEMANTIC_CASE_ID} uses comparison 'semantic', "
        "which is not supported yet.\n"
    )


def test_benchmark_compare_rejects_unsupported_comparison_before_runtime_bootstrap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    persist(
        create_semantic_dataset(),
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    forbid_runtime_bootstrap(monkeypatch)

    result = compare_benchmarks(
        benchmark_id=DATASET_ID,
        workflow_ids=(FIRST_WORKFLOW_ID, SECOND_WORKFLOW_ID),
        output_name="classification",
        target_latency_seconds=60.0,
        target_cost_usd=0.01,
    )

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert captured.err == (
        f"Benchmark case {SEMANTIC_CASE_ID} uses comparison 'semantic', "
        "which is not supported yet.\n"
    )
