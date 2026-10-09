"""Tests for labeling persisted runs by the operation that produced them."""

from pathlib import Path
from uuid import UUID

import pytest

from azathoth.cli import list_workflow_runs
from azathoth.workflows import (
    SQLiteWorkflowExperimentRepository,
    WorkflowCandidateSignature,
    WorkflowExperimentObservation,
    WorkflowExperimentRecord,
    WorkflowScorecard,
)
from tests.cli.test_run_commands import (
    FIRST_RUN_ID,
    SECOND_RUN_ID,
    STRATEGY_ID,
    THIRD_RUN_ID,
    WORKFLOW_ID,
    configure_database,
    create_metadata,
    save_history,
)

EXPERIMENT_ID = UUID("55555555-5555-4555-8555-555555555551")


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
        run_id=run_id,
        evaluation_id=UUID(int=run_id.int + (1 << 64)),
        scorecard=WorkflowScorecard(
            quality_score=overall_score,
            reliability_score=overall_score,
            latency_score=overall_score,
            cost_score=overall_score,
            overall_score=overall_score,
        ),
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
