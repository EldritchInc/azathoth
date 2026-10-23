"""Tests for labeling persisted runs by the operation that produced them."""

from pathlib import Path
from uuid import UUID

import pytest

from azathoth.cli import list_workflow_runs
from azathoth.evaluation import OutcomeComparison
from azathoth.workflows import (
    SQLiteWorkflowBenchmarkExecutionRepository,
    SQLiteWorkflowExperimentRepository,
    WorkflowBenchmarkExecutionCandidate,
    WorkflowBenchmarkExecutionCase,
    WorkflowBenchmarkExecutionKind,
    WorkflowBenchmarkExecutionRecord,
    WorkflowCandidateSignature,
    WorkflowExperimentCaseObservation,
    WorkflowExperimentObservation,
    WorkflowExperimentRecord,
    WorkflowScorecard,
    WorkflowScoringPolicy,
)
from tests.cli.test_run_commands import (
    FIRST_RUN_ID,
    OTHER_RUN_ID,
    OTHER_WORKFLOW_ID,
    SECOND_RUN_ID,
    STRATEGY_ID,
    THIRD_RUN_ID,
    WORKFLOW_ID,
    configure_database,
    create_metadata,
    save_history,
)

EXPERIMENT_ID = UUID("55555555-5555-4555-8555-555555555551")

BENCHMARK_ID = UUID("66666666-6666-4666-8666-666666666661")

CASE_ID = UUID("66666666-6666-4666-8666-666666666662")


def create_observation(
    run_id: UUID,
    *,
    overall_score: float,
) -> WorkflowExperimentObservation:
    """Create one experiment observation of a persisted run."""

    return WorkflowExperimentObservation(
        workflow=create_metadata(),
        candidate_signature=WorkflowCandidateSignature(
            workflow_id=WORKFLOW_ID,
            strategy_ids=(STRATEGY_ID,),
        ),
        id=run_id,
        cases=(
            WorkflowExperimentCaseObservation(
                run_id=run_id,
                evaluation_id=UUID(int=run_id.int + (1 << 64)),
            ),
        ),
        scorecard=WorkflowScorecard(
            quality_score=overall_score,
            reliability_score=overall_score,
            latency_score=overall_score,
            cost_score=overall_score,
            overall_score=overall_score,
        ),
    )


def create_benchmark_candidate(
    run_id: UUID,
    *,
    workflow_id: UUID = WORKFLOW_ID,
    overall_score: float | None = None,
) -> WorkflowBenchmarkExecutionCandidate:
    """Create one benchmark execution candidate that produced one persisted run."""

    return WorkflowBenchmarkExecutionCandidate(
        workflow=create_metadata(workflow_id),
        candidate_signature=WorkflowCandidateSignature(
            workflow_id=workflow_id,
            strategy_ids=(STRATEGY_ID,),
        ),
        cases=(
            WorkflowBenchmarkExecutionCase(
                case_id=CASE_ID,
                comparison=OutcomeComparison.EXACT,
                run_id=run_id,
                evaluation_id=UUID(int=run_id.int + (1 << 64)),
                passed=True,
            ),
        ),
        scorecard=(
            WorkflowScorecard(
                quality_score=overall_score,
                reliability_score=overall_score,
                latency_score=overall_score,
                cost_score=overall_score,
                overall_score=overall_score,
            )
            if overall_score is not None
            else None
        ),
    )


def save_benchmark_run(
    database: Path,
    run_id: UUID,
) -> None:
    """Record one benchmark run execution that produced one persisted run."""

    SQLiteWorkflowBenchmarkExecutionRepository(database).save(
        WorkflowBenchmarkExecutionRecord(
            benchmark_id=BENCHMARK_ID,
            kind=WorkflowBenchmarkExecutionKind.RUN,
            candidates=(create_benchmark_candidate(run_id),),
        )
    )


def run_sources(
    output: str,
) -> list[tuple[str, str]]:
    """Return each listed run ID with its source column."""

    return [(line.split()[0], line.split()[-2]) for line in output.splitlines()]


def test_list_workflow_runs_labels_runs_observed_by_experiments(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_database(
        monkeypatch,
        tmp_path,
    )

    save_history(database)

    SQLiteWorkflowExperimentRepository(database).save(
        WorkflowExperimentRecord(
            id=EXPERIMENT_ID,
            observations=(
                create_observation(
                    FIRST_RUN_ID,
                    overall_score=0.9,
                ),
            ),
            ranking=(FIRST_RUN_ID,),
        )
    )

    result = list_workflow_runs(WORKFLOW_ID)

    captured = capsys.readouterr()

    assert result == 0
    assert run_sources(captured.out) == [
        (str(THIRD_RUN_ID), "configured"),
        (str(SECOND_RUN_ID), "production"),
        (str(FIRST_RUN_ID), "experiment"),
    ]


def test_production_association_takes_precedence_over_experiment_observation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_database(
        monkeypatch,
        tmp_path,
    )

    save_history(database)

    SQLiteWorkflowExperimentRepository(database).save(
        WorkflowExperimentRecord(
            id=EXPERIMENT_ID,
            observations=(
                create_observation(
                    SECOND_RUN_ID,
                    overall_score=0.9,
                ),
            ),
            ranking=(SECOND_RUN_ID,),
        )
    )

    result = list_workflow_runs(WORKFLOW_ID)

    captured = capsys.readouterr()

    assert result == 0
    assert (str(SECOND_RUN_ID), "production") in run_sources(captured.out)


def test_list_workflow_runs_labels_runs_recorded_by_benchmark_runs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_database(
        monkeypatch,
        tmp_path,
    )

    save_history(database)

    save_benchmark_run(
        database,
        FIRST_RUN_ID,
    )

    result = list_workflow_runs(WORKFLOW_ID)

    captured = capsys.readouterr()

    assert result == 0
    assert run_sources(captured.out) == [
        (str(THIRD_RUN_ID), "configured"),
        (str(SECOND_RUN_ID), "production"),
        (str(FIRST_RUN_ID), "benchmark"),
    ]


def test_list_workflow_runs_labels_runs_recorded_by_benchmark_comparisons(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_database(
        monkeypatch,
        tmp_path,
    )

    save_history(database)

    candidates = (
        create_benchmark_candidate(
            THIRD_RUN_ID,
            overall_score=0.9,
        ),
        create_benchmark_candidate(
            OTHER_RUN_ID,
            workflow_id=OTHER_WORKFLOW_ID,
            overall_score=0.4,
        ),
    )

    SQLiteWorkflowBenchmarkExecutionRepository(database).save(
        WorkflowBenchmarkExecutionRecord(
            benchmark_id=BENCHMARK_ID,
            kind=WorkflowBenchmarkExecutionKind.COMPARE,
            candidates=candidates,
            ranking=tuple(candidate.id for candidate in candidates),
            scoring_policy=WorkflowScoringPolicy(
                target_latency_seconds=1.0,
                target_cost_usd=0.01,
            ),
        )
    )

    result = list_workflow_runs(WORKFLOW_ID)

    captured = capsys.readouterr()

    assert result == 0
    assert run_sources(captured.out) == [
        (str(THIRD_RUN_ID), "benchmark"),
        (str(SECOND_RUN_ID), "production"),
        (str(FIRST_RUN_ID), "configured"),
    ]


def test_production_association_takes_precedence_over_benchmark_execution(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_database(
        monkeypatch,
        tmp_path,
    )

    save_history(database)

    save_benchmark_run(
        database,
        SECOND_RUN_ID,
    )

    result = list_workflow_runs(WORKFLOW_ID)

    captured = capsys.readouterr()

    assert result == 0
    assert (str(SECOND_RUN_ID), "production") in run_sources(captured.out)
