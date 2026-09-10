"""Tests for comparing durable benchmarks through the CLI."""

from pathlib import Path
from uuid import UUID

import pytest

import azathoth.cli.benchmarks as benchmark_commands
from azathoth.cli import (
    DATABASE_ENVIRONMENT_VARIABLE,
    compare_benchmarks,
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
    WorkflowBenchmarkRankedCandidate,
    WorkflowBenchmarkRanking,
    WorkflowGenerationError,
    WorkflowScorecard,
    WorkflowScoringPolicy,
)

BENCHMARK_ID = UUID("11111111-1111-1111-1111-111111111111")

UNKNOWN_BENCHMARK_ID = UUID("99999999-9999-9999-9999-999999999999")

FIRST_WORKFLOW_ID = UUID("22222222-2222-2222-2222-222222222222")

SECOND_WORKFLOW_ID = UUID("33333333-3333-3333-3333-333333333333")

CASE_ID = UUID("44444444-4444-4444-4444-444444444444")


def create_dataset() -> BenchmarkDataset:
    """Create one deterministic durable benchmark."""

    return BenchmarkDataset(
        id=BENCHMARK_ID,
        name="classification",
        description="Compare configured classification workflows.",
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


def create_ranking() -> WorkflowBenchmarkRanking:
    """Create deterministic benchmark ranking evidence."""

    return WorkflowBenchmarkRanking(
        entries=(
            WorkflowBenchmarkRankedCandidate(
                rank=1,
                name=str(FIRST_WORKFLOW_ID),
                scorecard=WorkflowScorecard(
                    quality_score=1.0,
                    reliability_score=1.0,
                    latency_score=1.0,
                    cost_score=1.0,
                    overall_score=1.0,
                ),
            ),
            WorkflowBenchmarkRankedCandidate(
                rank=2,
                name=str(SECOND_WORKFLOW_ID),
                scorecard=WorkflowScorecard(
                    quality_score=0.5,
                    reliability_score=1.0,
                    latency_score=1.0,
                    cost_score=1.0,
                    overall_score=0.875,
                ),
            ),
        )
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


def test_benchmark_compare_executes_configured_workflows(
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
            tuple[UUID, ...],
            BenchmarkDataset,
            str,
            WorkflowScoringPolicy,
        ]
    ] = []

    ranking = create_ranking()

    async def fake_compare_configured_benchmarks(
        *,
        runtime: object,
        workflow_ids: tuple[UUID, ...],
        dataset: BenchmarkDataset,
        output_name: str,
        scoring_policy: WorkflowScoringPolicy,
    ) -> WorkflowBenchmarkRanking:
        calls.append(
            (
                runtime,
                workflow_ids,
                dataset,
                output_name,
                scoring_policy,
            )
        )

        return ranking

    monkeypatch.setattr(
        benchmark_commands,
        "compare_configured_benchmarks",
        fake_compare_configured_benchmarks,
    )

    monkeypatch.setattr(
        benchmark_commands,
        "render_workflow_benchmark_ranking",
        lambda ranking, *, benchmark_id: f"rendered {benchmark_id} {ranking.winner.name}",
    )

    status = compare_benchmarks(
        benchmark_id=BENCHMARK_ID,
        workflow_ids=(
            FIRST_WORKFLOW_ID,
            SECOND_WORKFLOW_ID,
        ),
        output_name="classification",
        target_latency_seconds=5.0,
        target_cost_usd=0.001,
    )

    captured = capsys.readouterr()

    assert status == 0

    assert len(calls) == 1

    (
        received_runtime,
        received_workflows,
        received_dataset,
        received_output,
        received_policy,
    ) = calls[0]

    assert received_runtime is runtime

    assert received_workflows == (
        FIRST_WORKFLOW_ID,
        SECOND_WORKFLOW_ID,
    )

    assert received_dataset == create_dataset()
    assert received_output == "classification"

    assert received_policy == WorkflowScoringPolicy(
        target_latency_seconds=5.0,
        target_cost_usd=0.001,
    )

    assert captured.out == (f"rendered {BENCHMARK_ID} {FIRST_WORKFLOW_ID}\n")

    assert captured.err == ""


def test_benchmark_compare_rejects_unknown_dataset_before_runtime_bootstrap(
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

    status = compare_benchmarks(
        benchmark_id=UNKNOWN_BENCHMARK_ID,
        workflow_ids=(
            FIRST_WORKFLOW_ID,
            SECOND_WORKFLOW_ID,
        ),
        output_name="classification",
        target_latency_seconds=5.0,
        target_cost_usd=0.001,
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
        (
            ValueError("At least two configured workflows are required for benchmark comparison."),
            ("At least two configured workflows are required for benchmark comparison."),
        ),
    ),
)
def test_benchmark_compare_reports_operator_errors(
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

    async def fail_compare_configured_benchmarks(
        **_kwargs: object,
    ) -> WorkflowBenchmarkRanking:
        raise error

    monkeypatch.setattr(
        benchmark_commands,
        "compare_configured_benchmarks",
        fail_compare_configured_benchmarks,
    )

    status = compare_benchmarks(
        benchmark_id=BENCHMARK_ID,
        workflow_ids=(
            FIRST_WORKFLOW_ID,
            SECOND_WORKFLOW_ID,
        ),
        output_name="classification",
        target_latency_seconds=5.0,
        target_cost_usd=0.001,
    )

    captured = capsys.readouterr()

    assert status == 1
    assert captured.out == ""
    assert captured.err == f"{message}\n"
