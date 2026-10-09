"""Tests for workflow experiment inspection commands."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest

from azathoth.cli import (
    DATABASE_ENVIRONMENT_VARIABLE,
    list_workflow_experiments,
    show_experiment,
)
from azathoth.prompting import (
    FixedModelSelection,
    PromptStrategySpec,
)
from azathoth.providers import Prompt
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    SQLiteWorkflowExperimentRepository,
    SQLiteWorkflowRepository,
    WorkflowCandidateSignature,
    WorkflowExperimentObservation,
    WorkflowExperimentRecord,
    WorkflowMetadata,
    WorkflowScorecard,
    WorkflowSpecification,
    WorkflowStepSpecification,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

OTHER_WORKFLOW_ID = UUID("22222222-2222-2222-2222-222222222222")

UNKNOWN_WORKFLOW_ID = UUID("33333333-3333-3333-3333-333333333333")

STEP_ID = UUID("44444444-4444-4444-4444-444444444444")

STRATEGY_ID = UUID("77777777-7777-7777-7777-777777777777")

FIRST_EXPERIMENT_ID = UUID("55555555-5555-4555-8555-555555555551")

SECOND_EXPERIMENT_ID = UUID("55555555-5555-4555-8555-555555555552")

THIRD_EXPERIMENT_ID = UUID("55555555-5555-4555-8555-555555555553")

OTHER_EXPERIMENT_ID = UUID("55555555-5555-4555-8555-555555555554")

UNKNOWN_EXPERIMENT_ID = UUID("55555555-5555-4555-8555-555555555559")

RECORDED_AT = datetime(
    2026,
    10,
    9,
    16,
    0,
    tzinfo=UTC,
)


def configure_database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Path:
    """Point the CLI at an isolated durable database."""

    database = tmp_path / "azathoth.db"

    monkeypatch.setenv(
        DATABASE_ENVIRONMENT_VARIABLE,
        str(database),
    )

    return database


def create_metadata(
    workflow_id: UUID = WORKFLOW_ID,
) -> WorkflowMetadata:
    """Create deterministic workflow metadata."""

    return WorkflowMetadata(
        id=workflow_id,
        name="experimented workflow",
        description="Workflow used to test experiment inspection.",
        version="1.0.0",
    )


def create_workflow() -> WorkflowSpecification:
    """Create one configured workflow with no experiment history."""

    return WorkflowSpecification(
        metadata=create_metadata(),
        steps=(
            WorkflowStepSpecification(
                id=STEP_ID,
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=STRATEGY_ID,
                        name="Experimented prompt",
                        description="Experimented prompt description.",
                        version="1.0.0",
                    ),
                    prompt=Prompt(
                        text="Return exactly OK.",
                    ),
                    model_selection=FixedModelSelection(
                        provider="openrouter",
                        model="example-model",
                    ),
                ),
            ),
        ),
    )


def create_experiment(
    experiment_id: UUID,
    *,
    workflow_id: UUID = WORKFLOW_ID,
    recorded_at: datetime = RECORDED_AT,
) -> WorkflowExperimentRecord:
    """Create one single-candidate experiment record."""

    run_id = UUID(int=experiment_id.int + (1 << 64))

    return WorkflowExperimentRecord(
        id=experiment_id,
        observations=(
            WorkflowExperimentObservation(
                workflow=create_metadata(workflow_id),
                candidate_signature=WorkflowCandidateSignature(
                    workflow_id=workflow_id,
                    strategy_ids=(STRATEGY_ID,),
                ),
                run_id=run_id,
                evaluation_id=UUID(int=experiment_id.int + (2 << 64)),
                scorecard=WorkflowScorecard(
                    quality_score=1.0,
                    reliability_score=1.0,
                    latency_score=1.0,
                    cost_score=1.0,
                    overall_score=1.0,
                ),
            ),
        ),
        ranking=(run_id,),
        recorded_at=recorded_at,
    )


def save_history(
    database: Path,
) -> None:
    """Persist three experiments of one workflow and one of another.

    Experiments are saved out of chronological order so listing must sort them.
    """

    repository = SQLiteWorkflowExperimentRepository(database)

    repository.save(
        create_experiment(
            SECOND_EXPERIMENT_ID,
            recorded_at=RECORDED_AT + timedelta(minutes=5),
        )
    )
    repository.save(create_experiment(FIRST_EXPERIMENT_ID))
    repository.save(
        create_experiment(
            THIRD_EXPERIMENT_ID,
            recorded_at=RECORDED_AT + timedelta(minutes=10),
        )
    )
    repository.save(
        create_experiment(
            OTHER_EXPERIMENT_ID,
            workflow_id=OTHER_WORKFLOW_ID,
        )
    )


def test_list_workflow_experiments_lists_newest_first(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_database(
        monkeypatch,
        tmp_path,
    )

    save_history(database)

    result = list_workflow_experiments(WORKFLOW_ID)

    captured = capsys.readouterr()

    assert result == 0
    assert captured.err == ""
    assert [line.split()[0] for line in captured.out.splitlines()] == [
        str(THIRD_EXPERIMENT_ID),
        str(SECOND_EXPERIMENT_ID),
        str(FIRST_EXPERIMENT_ID),
    ]


def test_list_workflow_experiments_applies_limit_after_sorting(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_database(
        monkeypatch,
        tmp_path,
    )

    save_history(database)

    result = list_workflow_experiments(
        WORKFLOW_ID,
        limit=2,
    )

    captured = capsys.readouterr()

    assert result == 0
    assert [line.split()[0] for line in captured.out.splitlines()] == [
        str(THIRD_EXPERIMENT_ID),
        str(SECOND_EXPERIMENT_ID),
    ]


def test_list_workflow_experiments_prints_nothing_for_configured_workflow_without_history(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_database(
        monkeypatch,
        tmp_path,
    )

    SQLiteWorkflowRepository(database).save(create_workflow())

    result = list_workflow_experiments(WORKFLOW_ID)

    captured = capsys.readouterr()

    assert result == 0
    assert captured.out == ""
    assert captured.err == ""


def test_list_workflow_experiments_lists_history_of_unconfigured_workflow(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_database(
        monkeypatch,
        tmp_path,
    )

    save_history(database)

    result = list_workflow_experiments(OTHER_WORKFLOW_ID)

    captured = capsys.readouterr()

    assert result == 0
    assert [line.split()[0] for line in captured.out.splitlines()] == [
        str(OTHER_EXPERIMENT_ID),
    ]


def test_list_workflow_experiments_rejects_unknown_workflow(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_database(
        monkeypatch,
        tmp_path,
    )

    save_history(database)

    result = list_workflow_experiments(UNKNOWN_WORKFLOW_ID)

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert captured.err == f"Workflow {UNKNOWN_WORKFLOW_ID} is not configured.\n"


def test_show_experiment_renders_persisted_experiment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_database(
        monkeypatch,
        tmp_path,
    )

    save_history(database)

    result = show_experiment(SECOND_EXPERIMENT_ID)

    captured = capsys.readouterr()

    assert result == 0
    assert captured.err == ""
    assert captured.out.startswith(f"Experiment ID: {SECOND_EXPERIMENT_ID}\n")
    assert "Rank 1\n" in captured.out
    assert f"Workflow ID: {WORKFLOW_ID}\n" in captured.out


def test_show_experiment_rejects_unknown_experiment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_database(
        monkeypatch,
        tmp_path,
    )

    save_history(database)

    result = show_experiment(UNKNOWN_EXPERIMENT_ID)

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert captured.err == f"Experiment {UNKNOWN_EXPERIMENT_ID} was not found.\n"
