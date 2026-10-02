"""Tests for workflow run inspection commands."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest

from azathoth.cli import (
    DATABASE_ENVIRONMENT_VARIABLE,
    list_workflow_runs,
    show_run,
)
from azathoth.context import Context
from azathoth.execution import ExecutionResult
from azathoth.prompting import (
    FixedModelSelection,
    PromptStrategySpec,
)
from azathoth.providers import Prompt
from azathoth.strategies import (
    StrategyMetadata,
    StrategyResourceBinding,
)
from azathoth.workflows import (
    ProductionInvocationRun,
    SQLiteProductionInvocationRunRepository,
    SQLiteWorkflowRepository,
    SQLiteWorkflowRunFeedbackRepository,
    SQLiteWorkflowRunRepository,
    WorkflowMetadata,
    WorkflowRun,
    WorkflowRunFeedback,
    WorkflowRunFeedbackDisposition,
    WorkflowSpecification,
    WorkflowStepAttempt,
    WorkflowStepRun,
    WorkflowStepSpecification,
    WorkflowStepStatus,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

OTHER_WORKFLOW_ID = UUID("22222222-2222-2222-2222-222222222222")

UNKNOWN_WORKFLOW_ID = UUID("33333333-3333-3333-3333-333333333333")

STEP_ID = UUID("44444444-4444-4444-4444-444444444444")

STRATEGY_ID = UUID("77777777-7777-7777-7777-777777777777")

FIRST_RUN_ID = UUID("99999999-9999-4999-8999-999999999991")

SECOND_RUN_ID = UUID("99999999-9999-4999-8999-999999999992")

THIRD_RUN_ID = UUID("99999999-9999-4999-8999-999999999993")

OTHER_RUN_ID = UUID("99999999-9999-4999-8999-999999999994")

UNKNOWN_RUN_ID = UUID("99999999-9999-4999-8999-999999999999")

INVOCATION_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")

MODEL_IDENTIFIER = "openrouter/example-model"

STARTED_AT = datetime(
    2026,
    10,
    2,
    12,
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
        name="inspected workflow",
        description="Workflow used to test run inspection.",
        version="1.0.0",
    )


def create_workflow() -> WorkflowSpecification:
    """Create one configured workflow with no run history."""

    return WorkflowSpecification(
        metadata=create_metadata(),
        steps=(
            WorkflowStepSpecification(
                id=STEP_ID,
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=STRATEGY_ID,
                        name="Inspected prompt",
                        description="Inspected prompt description.",
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


def create_run(
    run_id: UUID,
    *,
    workflow_id: UUID = WORKFLOW_ID,
    started_at: datetime = STARTED_AT,
) -> WorkflowRun:
    """Create one successful run that bound one model."""

    context = Context()
    completed_at = started_at + timedelta(seconds=1)

    execution = ExecutionResult(
        strategy_id=STRATEGY_ID,
        strategy_name="Inspected prompt",
        strategy_version="1.0.0",
        output="OK",
        resources=(
            StrategyResourceBinding(
                kind="model",
                identifier=MODEL_IDENTIFIER,
            ),
        ),
        initial_context=context,
        final_context=context,
        started_at=started_at,
        completed_at=completed_at,
    )

    return WorkflowRun(
        id=run_id,
        workflow=create_metadata(workflow_id),
        steps=(
            WorkflowStepRun(
                step_id=STEP_ID,
                layer_index=0,
                status=WorkflowStepStatus.EXECUTED,
                execution=execution,
                attempts=(
                    WorkflowStepAttempt(
                        attempt_number=1,
                        started_at=started_at,
                        completed_at=completed_at,
                        execution=execution,
                    ),
                ),
            ),
        ),
        initial_context=context,
        final_context=context,
        started_at=started_at,
        completed_at=completed_at,
    )


def save_history(
    database: Path,
) -> None:
    """Persist three runs of one workflow and one run of another.

    Runs are saved out of chronological order so listing must sort them. The
    middle run is associated with a production invocation.
    """

    repository = SQLiteWorkflowRunRepository(database)

    repository.save(
        create_run(
            SECOND_RUN_ID,
            started_at=STARTED_AT + timedelta(minutes=5),
        )
    )
    repository.save(create_run(FIRST_RUN_ID))
    repository.save(
        create_run(
            THIRD_RUN_ID,
            started_at=STARTED_AT + timedelta(minutes=10),
        )
    )
    repository.save(
        create_run(
            OTHER_RUN_ID,
            workflow_id=OTHER_WORKFLOW_ID,
        )
    )

    SQLiteProductionInvocationRunRepository(database).save(
        ProductionInvocationRun(
            invocation_id=INVOCATION_ID,
            run_id=SECOND_RUN_ID,
        )
    )


def test_list_workflow_runs_lists_newest_first_with_sources(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_database(
        monkeypatch,
        tmp_path,
    )

    save_history(database)

    result = list_workflow_runs(WORKFLOW_ID)

    captured = capsys.readouterr()

    assert result == 0
    assert captured.err == ""

    lines = captured.out.splitlines()

    assert [line.split()[0] for line in lines] == [
        str(THIRD_RUN_ID),
        str(SECOND_RUN_ID),
        str(FIRST_RUN_ID),
    ]
    assert [line.split()[-2] for line in lines] == [
        "configured",
        "production",
        "configured",
    ]
    assert [line.split()[-1] for line in lines] == [
        "-",
        "-",
        "-",
    ]


def test_list_workflow_runs_applies_limit_after_sorting(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_database(
        monkeypatch,
        tmp_path,
    )

    save_history(database)

    result = list_workflow_runs(
        WORKFLOW_ID,
        limit=2,
    )

    captured = capsys.readouterr()

    assert result == 0
    assert [line.split()[0] for line in captured.out.splitlines()] == [
        str(THIRD_RUN_ID),
        str(SECOND_RUN_ID),
    ]


def test_list_workflow_runs_prints_nothing_for_configured_workflow_without_runs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_database(
        monkeypatch,
        tmp_path,
    )

    SQLiteWorkflowRepository(database).save(create_workflow())

    result = list_workflow_runs(WORKFLOW_ID)

    captured = capsys.readouterr()

    assert result == 0
    assert captured.out == ""
    assert captured.err == ""


def test_list_workflow_runs_lists_history_of_unconfigured_workflow(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_database(
        monkeypatch,
        tmp_path,
    )

    save_history(database)

    result = list_workflow_runs(OTHER_WORKFLOW_ID)

    captured = capsys.readouterr()

    assert result == 0
    assert [line.split()[0] for line in captured.out.splitlines()] == [
        str(OTHER_RUN_ID),
    ]


def test_list_workflow_runs_rejects_unknown_workflow(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_database(
        monkeypatch,
        tmp_path,
    )

    save_history(database)

    result = list_workflow_runs(UNKNOWN_WORKFLOW_ID)

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert captured.err == f"Workflow {UNKNOWN_WORKFLOW_ID} is not configured.\n"


def test_list_workflow_runs_shows_latest_disposition_per_run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_database(
        monkeypatch,
        tmp_path,
    )

    save_history(database)

    feedback_repository = SQLiteWorkflowRunFeedbackRepository(database)

    feedback_repository.save(
        WorkflowRunFeedback(
            run_id=FIRST_RUN_ID,
            disposition=WorkflowRunFeedbackDisposition.BAD,
            reason="Wrong label.",
            created_at=STARTED_AT + timedelta(hours=1),
        )
    )
    feedback_repository.save(
        WorkflowRunFeedback(
            run_id=FIRST_RUN_ID,
            disposition=WorkflowRunFeedbackDisposition.GOOD,
            created_at=STARTED_AT + timedelta(hours=2),
        )
    )
    feedback_repository.save(
        WorkflowRunFeedback(
            run_id=THIRD_RUN_ID,
            disposition=WorkflowRunFeedbackDisposition.GOOD,
            created_at=STARTED_AT + timedelta(hours=4),
        )
    )
    feedback_repository.save(
        WorkflowRunFeedback(
            run_id=THIRD_RUN_ID,
            disposition=WorkflowRunFeedbackDisposition.BAD,
            reason="Recorded later but timestamped earlier.",
            created_at=STARTED_AT + timedelta(hours=3),
        )
    )

    result = list_workflow_runs(WORKFLOW_ID)

    captured = capsys.readouterr()

    assert result == 0
    assert [(line.split()[0], line.split()[-1]) for line in captured.out.splitlines()] == [
        (str(THIRD_RUN_ID), "good"),
        (str(SECOND_RUN_ID), "-"),
        (str(FIRST_RUN_ID), "good"),
    ]


def test_show_run_renders_persisted_run_with_resources(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_database(
        monkeypatch,
        tmp_path,
    )

    save_history(database)

    result = show_run(SECOND_RUN_ID)

    captured = capsys.readouterr()

    assert result == 0
    assert captured.err == ""
    assert f"Run ID: {SECOND_RUN_ID}\n" in captured.out
    assert f"Workflow ID: {WORKFLOW_ID}\n" in captured.out
    assert f"Resource: model {MODEL_IDENTIFIER}\n" in captured.out


def test_show_run_rejects_unknown_run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_database(
        monkeypatch,
        tmp_path,
    )

    save_history(database)

    result = show_run(UNKNOWN_RUN_ID)

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert captured.err == f"Run {UNKNOWN_RUN_ID} was not found.\n"
