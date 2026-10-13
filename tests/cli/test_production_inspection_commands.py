"""Tests for production deployment and invocation inspection commands."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest

from azathoth.cli import (
    DATABASE_ENVIRONMENT_VARIABLE,
    list_workflow_invocations,
    list_workflow_revisions,
    show_invocation,
    show_workflow_production,
)
from azathoth.prompting import (
    FixedModelSelection,
    PromptStrategySpec,
)
from azathoth.providers import Prompt
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    ProductionInvocation,
    ProductionInvocationErrorCode,
    ProductionInvocationFailure,
    ProductionInvocationRun,
    ProductionInvocationSuccess,
    SQLiteProductionInvocationRepository,
    SQLiteProductionInvocationRunRepository,
    SQLiteWorkflowProductionRevisionRepository,
    SQLiteWorkflowProductionStateRepository,
    SQLiteWorkflowRepository,
    WorkflowMetadata,
    WorkflowProductionRevision,
    WorkflowProductionState,
    WorkflowSpecification,
    WorkflowStepSpecification,
    create_production_invocation,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

OTHER_WORKFLOW_ID = UUID("22222222-2222-2222-2222-222222222222")

UNKNOWN_WORKFLOW_ID = UUID("33333333-3333-3333-3333-333333333333")

STEP_ID = UUID("44444444-4444-4444-4444-444444444444")

STRATEGY_ID = UUID("77777777-7777-7777-7777-777777777777")

FIRST_REVISION_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1")

SECOND_REVISION_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa2")

THIRD_REVISION_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa3")

OTHER_REVISION_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa4")

FIRST_RUN_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb1")

UNKNOWN_INVOCATION_ID = UUID("cccccccc-cccc-4ccc-8ccc-ccccccccccc9")

CREATED_AT = datetime(
    2026,
    10,
    9,
    17,
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


def create_workflow(
    model: str = "first-model",
    *,
    workflow_id: UUID = WORKFLOW_ID,
) -> WorkflowSpecification:
    """Create one single-prompt workflow pinned to one model."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=workflow_id,
            name="deployed workflow",
            description="Workflow used to test production inspection.",
            version="1.0.0",
        ),
        steps=(
            WorkflowStepSpecification(
                id=STEP_ID,
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=STRATEGY_ID,
                        name="Deployed prompt",
                        description="Deployed prompt description.",
                        version="1.0.0",
                    ),
                    prompt=Prompt(
                        text="Return exactly OK.",
                    ),
                    model_selection=FixedModelSelection(
                        provider="openrouter",
                        model=model,
                    ),
                ),
            ),
        ),
    )


def create_state(
    model: str = "first-model",
    *,
    workflow_id: UUID = WORKFLOW_ID,
) -> WorkflowProductionState:
    """Create production state for one single-prompt workflow."""

    return WorkflowProductionState(
        specification=create_workflow(
            model,
            workflow_id=workflow_id,
        ),
    )


def save_deployment_history(
    database: Path,
) -> None:
    """Persist three revisions of one workflow and one of another.

    Revisions are saved out of chronological order so listing must sort them.
    The second revision is active, so the newest revision is not assumed active.
    """

    revisions = SQLiteWorkflowProductionRevisionRepository(database)

    revisions.save(
        WorkflowProductionRevision(
            id=THIRD_REVISION_ID,
            state=create_state("third-model"),
            created_at=CREATED_AT + timedelta(minutes=10),
        )
    )
    revisions.save(
        WorkflowProductionRevision(
            id=FIRST_REVISION_ID,
            state=create_state("first-model"),
            created_at=CREATED_AT,
        )
    )
    revisions.save(
        WorkflowProductionRevision(
            id=SECOND_REVISION_ID,
            state=create_state("second-model"),
            created_at=CREATED_AT + timedelta(minutes=5),
        )
    )
    revisions.save(
        WorkflowProductionRevision(
            id=OTHER_REVISION_ID,
            state=create_state(workflow_id=OTHER_WORKFLOW_ID),
            created_at=CREATED_AT,
        )
    )

    SQLiteWorkflowProductionStateRepository(database).set(
        create_state("second-model"),
    )


def save_invocation(
    database: Path,
    text: str,
    *,
    created_at: datetime,
    workflow_id: UUID = WORKFLOW_ID,
) -> ProductionInvocation:
    """Persist one production invocation with a deterministic creation time."""

    invocation = create_production_invocation(
        workflow_id=workflow_id,
        payload={"text": text},
        caller_metadata={"caller": "billing-service"},
    ).model_copy(
        update={
            "created_at": created_at,
        }
    )

    SQLiteProductionInvocationRepository(database).save(invocation)

    return invocation


def save_invocation_history(
    database: Path,
) -> tuple[ProductionInvocation, ProductionInvocation, ProductionInvocation]:
    """Persist a succeeded, a failed, and a pending invocation out of order."""

    failed = save_invocation(
        database,
        "second",
        created_at=CREATED_AT + timedelta(minutes=5),
    )
    succeeded = save_invocation(
        database,
        "first",
        created_at=CREATED_AT,
    )
    pending = save_invocation(
        database,
        "third",
        created_at=CREATED_AT + timedelta(minutes=10),
    )

    save_invocation(
        database,
        "other",
        created_at=CREATED_AT,
        workflow_id=OTHER_WORKFLOW_ID,
    )

    invocations = SQLiteProductionInvocationRepository(database)

    invocations.save_result(
        ProductionInvocationSuccess(
            invocation_id=succeeded.id,
            result={"answer": "OK"},
        )
    )
    invocations.save_result(
        ProductionInvocationFailure(
            invocation_id=failed.id,
            error_code=ProductionInvocationErrorCode.TIMEOUT,
            message="Workflow timed out.",
        )
    )

    SQLiteProductionInvocationRunRepository(database).save(
        ProductionInvocationRun(
            invocation_id=succeeded.id,
            run_id=FIRST_RUN_ID,
        )
    )

    return succeeded, failed, pending


def test_show_workflow_production_renders_active_revision(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_database(
        monkeypatch,
        tmp_path,
    )

    save_deployment_history(database)

    result = show_workflow_production(WORKFLOW_ID)

    captured = capsys.readouterr()

    assert result == 0
    assert captured.err == ""
    assert f"Revision ID: {SECOND_REVISION_ID}\n" in captured.out
    assert "Primary Model: openrouter/second-model\n" in captured.out


def test_show_workflow_production_without_recorded_revision(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_database(
        monkeypatch,
        tmp_path,
    )

    SQLiteWorkflowProductionStateRepository(database).set(create_state())

    result = show_workflow_production(WORKFLOW_ID)

    captured = capsys.readouterr()

    assert result == 0
    assert "Revision ID: unrecorded\n" in captured.out


def test_show_workflow_production_rejects_configured_workflow_not_in_production(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_database(
        monkeypatch,
        tmp_path,
    )

    SQLiteWorkflowRepository(database).save(create_workflow())

    result = show_workflow_production(WORKFLOW_ID)

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert captured.err == f"Workflow {WORKFLOW_ID} is not in production.\n"


def test_show_workflow_production_rejects_unknown_workflow(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_database(
        monkeypatch,
        tmp_path,
    )

    result = show_workflow_production(UNKNOWN_WORKFLOW_ID)

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert captured.err == f"Workflow {UNKNOWN_WORKFLOW_ID} is not configured.\n"


def test_list_workflow_revisions_lists_newest_first_and_marks_active(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_database(
        monkeypatch,
        tmp_path,
    )

    save_deployment_history(database)

    result = list_workflow_revisions(WORKFLOW_ID)

    captured = capsys.readouterr()

    assert result == 0
    assert captured.err == ""
    assert [line.split()[0] for line in captured.out.splitlines()] == [
        str(THIRD_REVISION_ID),
        str(SECOND_REVISION_ID),
        str(FIRST_REVISION_ID),
    ]
    assert [line.split()[2] for line in captured.out.splitlines()] == [
        "-",
        "active",
        "-",
    ]


def test_list_workflow_revisions_applies_limit_after_sorting(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_database(
        monkeypatch,
        tmp_path,
    )

    save_deployment_history(database)

    result = list_workflow_revisions(
        WORKFLOW_ID,
        limit=1,
    )

    captured = capsys.readouterr()

    assert result == 0
    assert [line.split()[0] for line in captured.out.splitlines()] == [
        str(THIRD_REVISION_ID),
    ]


def test_list_workflow_revisions_prints_nothing_for_configured_workflow_without_history(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_database(
        monkeypatch,
        tmp_path,
    )

    SQLiteWorkflowRepository(database).save(create_workflow())

    result = list_workflow_revisions(WORKFLOW_ID)

    captured = capsys.readouterr()

    assert result == 0
    assert captured.out == ""
    assert captured.err == ""


def test_list_workflow_revisions_lists_history_of_unconfigured_workflow(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_database(
        monkeypatch,
        tmp_path,
    )

    save_deployment_history(database)

    result = list_workflow_revisions(OTHER_WORKFLOW_ID)

    captured = capsys.readouterr()

    assert result == 0
    assert [line.split()[:3] for line in captured.out.splitlines()] == [
        [str(OTHER_REVISION_ID), CREATED_AT.isoformat(), "-"],
    ]


def test_list_workflow_revisions_rejects_unknown_workflow(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_database(
        monkeypatch,
        tmp_path,
    )

    save_deployment_history(database)

    result = list_workflow_revisions(UNKNOWN_WORKFLOW_ID)

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert captured.err == f"Workflow {UNKNOWN_WORKFLOW_ID} is not configured.\n"


def test_list_workflow_invocations_lists_newest_first_with_outcomes_and_runs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_database(
        monkeypatch,
        tmp_path,
    )

    succeeded, failed, pending = save_invocation_history(database)

    result = list_workflow_invocations(WORKFLOW_ID)

    captured = capsys.readouterr()

    lines = captured.out.splitlines()

    assert result == 0
    assert captured.err == ""
    assert [line.split()[0] for line in lines] == [
        str(pending.id),
        str(failed.id),
        str(succeeded.id),
    ]
    assert [line.split()[2] for line in lines] == [
        "pending",
        "timeout",
        "succeeded",
    ]
    assert lines[0].endswith("  no run")
    assert lines[1].endswith("  no run")
    assert lines[2].endswith(f"  {FIRST_RUN_ID}")


def test_list_workflow_invocations_applies_limit_after_sorting(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_database(
        monkeypatch,
        tmp_path,
    )

    _succeeded, failed, pending = save_invocation_history(database)

    result = list_workflow_invocations(
        WORKFLOW_ID,
        limit=2,
    )

    captured = capsys.readouterr()

    assert result == 0
    assert [line.split()[0] for line in captured.out.splitlines()] == [
        str(pending.id),
        str(failed.id),
    ]


def test_list_workflow_invocations_prints_nothing_for_configured_workflow_without_history(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_database(
        monkeypatch,
        tmp_path,
    )

    SQLiteWorkflowRepository(database).save(create_workflow())

    result = list_workflow_invocations(WORKFLOW_ID)

    captured = capsys.readouterr()

    assert result == 0
    assert captured.out == ""
    assert captured.err == ""


def test_list_workflow_invocations_lists_history_of_unconfigured_workflow(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_database(
        monkeypatch,
        tmp_path,
    )

    save_invocation_history(database)

    result = list_workflow_invocations(OTHER_WORKFLOW_ID)

    captured = capsys.readouterr()

    assert result == 0
    assert len(captured.out.splitlines()) == 1
    assert captured.out.split()[2] == "pending"


def test_list_workflow_invocations_rejects_unknown_workflow(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_database(
        monkeypatch,
        tmp_path,
    )

    save_invocation_history(database)

    result = list_workflow_invocations(UNKNOWN_WORKFLOW_ID)

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert captured.err == f"Workflow {UNKNOWN_WORKFLOW_ID} is not configured.\n"


def test_show_invocation_renders_input_result_and_run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_database(
        monkeypatch,
        tmp_path,
    )

    succeeded, _failed, _pending = save_invocation_history(database)

    result = show_invocation(succeeded.id)

    captured = capsys.readouterr()

    assert result == 0
    assert captured.err == ""
    assert captured.out.startswith(f"Invocation ID: {succeeded.id}\n")
    assert "Outcome: succeeded\n" in captured.out
    assert f"Run ID: {FIRST_RUN_ID}\n" in captured.out
    assert '"caller": "billing-service"' in captured.out
    assert '"text": "first"' in captured.out
    assert '"answer": "OK"' in captured.out


def test_show_invocation_renders_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_database(
        monkeypatch,
        tmp_path,
    )

    _succeeded, failed, _pending = save_invocation_history(database)

    result = show_invocation(failed.id)

    captured = capsys.readouterr()

    assert result == 0
    assert "Outcome: timeout\n" in captured.out
    assert "Run ID: no run\n" in captured.out
    assert "Message: Workflow timed out.\n" in captured.out


def test_show_invocation_rejects_unknown_invocation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_database(
        monkeypatch,
        tmp_path,
    )

    save_invocation_history(database)

    result = show_invocation(UNKNOWN_INVOCATION_ID)

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert captured.err == f"Invocation {UNKNOWN_INVOCATION_ID} was not found.\n"
