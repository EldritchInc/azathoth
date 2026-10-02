"""Tests for running configured workflows through the CLI."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

import azathoth.cli.workflows as workflow_commands
from azathoth.cli import (
    DATABASE_ENVIRONMENT_VARIABLE,
    run_workflow,
)
from azathoth.context import Context
from azathoth.prompting import (
    PortfolioModelSelection,
    PromptStrategySpec,
)
from azathoth.providers import (
    DeterministicLanguageModel,
    LanguageModelRegistry,
    ModelCatalog,
    ModelMetadata,
    ModelRequirements,
    Prompt,
)
from azathoth.runtime import AzathothRuntime
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    SQLiteWorkflowRunRepository,
    WorkflowCatalog,
    WorkflowMetadata,
    WorkflowRun,
    WorkflowSpecification,
    WorkflowStepAttempt,
    WorkflowStepFailure,
    WorkflowStepRun,
    WorkflowStepSpecification,
    WorkflowStepStatus,
)
from tests.model_authorization import (
    portfolio_for_catalog,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

UNKNOWN_WORKFLOW_ID = UUID("99999999-9999-9999-9999-999999999999")

STEP_ID = UUID("22222222-2222-2222-2222-222222222222")

STRATEGY_ID = UUID("33333333-3333-3333-3333-333333333333")

MODEL_IDENTIFIER = "test/example"


def create_workflow() -> WorkflowSpecification:
    """Create one workflow for CLI execution."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="CLI execution",
            description=("Exercise workflow execution through the CLI."),
            version="1.0.0",
        ),
        steps=(
            WorkflowStepSpecification(
                id=STEP_ID,
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=STRATEGY_ID,
                        name="CLI prompt",
                        description=("Execute one deterministic CLI prompt."),
                        version="1.0.0",
                    ),
                    prompt=Prompt(
                        text="Return success.",
                    ),
                    model_selection=PortfolioModelSelection(
                        requirements=ModelRequirements(),
                    ),
                ),
            ),
        ),
    )


def create_runtime() -> AzathothRuntime:
    """Create one deterministic executable runtime."""

    models = ModelCatalog(
        models=(
            ModelMetadata(
                provider="test",
                model="example",
                display_name="Example Model",
                context_window_tokens=8_192,
            ),
        )
    )

    return AzathothRuntime(
        workflows=WorkflowCatalog(specifications=(create_workflow(),)),
        models=models,
        portfolio=portfolio_for_catalog(models),
        language_models=LanguageModelRegistry(
            models={
                MODEL_IDENTIFIER: DeterministicLanguageModel(
                    provider="test",
                    model="example",
                    response_text="success",
                ),
            }
        ),
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


def configure_runtime(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    runtime: AzathothRuntime,
) -> Path:
    """Replace CLI runtime bootstrap with one deterministic runtime."""

    database = configure_database(
        monkeypatch,
        tmp_path,
    )

    monkeypatch.setattr(
        workflow_commands,
        "load_runtime",
        lambda _configuration: runtime,
    )

    return database


def create_failed_run() -> WorkflowRun:
    """Create one completed but unsuccessful configured workflow run."""

    now = datetime.now(tz=UTC)

    return WorkflowRun(
        workflow=create_workflow().metadata,
        steps=(
            WorkflowStepRun(
                step_id=STEP_ID,
                layer_index=0,
                status=WorkflowStepStatus.FAILED,
                attempts=(
                    WorkflowStepAttempt(
                        attempt_number=1,
                        started_at=now,
                        completed_at=now,
                        failure=WorkflowStepFailure(
                            exception_type="RuntimeError",
                            message="Execution failed.",
                        ),
                    ),
                ),
            ),
        ),
        initial_context=Context(),
        final_context=Context(),
        started_at=now,
        completed_at=now,
    )


def configure_failed_execution(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    failed: WorkflowRun,
) -> Path:
    """Replace configured execution with one deterministic failed run."""

    database = configure_database(
        monkeypatch,
        tmp_path,
    )

    async def fake_execute_configured_workflow(
        **_kwargs: object,
    ) -> WorkflowRun:
        return failed

    monkeypatch.setattr(
        workflow_commands,
        "load_runtime",
        lambda _configuration: object(),
    )
    monkeypatch.setattr(
        workflow_commands,
        "execute_configured_workflow",
        fake_execute_configured_workflow,
    )

    return database


def test_workflow_run_renders_completed_execution(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_runtime(
        monkeypatch,
        tmp_path,
        create_runtime(),
    )

    result = run_workflow(WORKFLOW_ID)

    captured = capsys.readouterr()

    assert result == 0
    assert captured.err == ""

    assert "Workflow: CLI execution\n" in captured.out

    assert f"Workflow ID: {WORKFLOW_ID}\n" in captured.out

    assert "Status: succeeded\n" in captured.out
    assert "Steps: 1\n" in captured.out
    assert "Executed: 1\n" in captured.out

    assert f"Strategy: CLI prompt [{MODEL_IDENTIFIER}]\n" in captured.out

    assert 'Output:\n"success"\n' in captured.out


def test_workflow_run_reports_unknown_workflow(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_runtime(
        monkeypatch,
        tmp_path,
        create_runtime(),
    )

    result = run_workflow(UNKNOWN_WORKFLOW_ID)

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""

    assert captured.err == (f"Workflow {UNKNOWN_WORKFLOW_ID} is not configured.\n")


def test_workflow_run_reports_non_executable_workflow(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    models = ModelCatalog(
        models=(
            ModelMetadata(
                provider="test",
                model="example",
                display_name="Example Model",
                context_window_tokens=8_192,
            ),
        )
    )

    runtime = AzathothRuntime(
        workflows=WorkflowCatalog(specifications=(create_workflow(),)),
        models=models,
        portfolio=portfolio_for_catalog(models),
        language_models=LanguageModelRegistry(),
    )

    configure_runtime(
        monkeypatch,
        tmp_path,
        runtime,
    )

    result = run_workflow(WORKFLOW_ID)

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""

    assert (
        "No executable prompt candidate could be generated "
        f"for workflow step {STEP_ID}." in captured.err
    )


def test_workflow_run_renders_failed_run_and_returns_nonzero(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_failed_execution(
        monkeypatch,
        tmp_path,
        create_failed_run(),
    )

    result = run_workflow(WORKFLOW_ID)

    captured = capsys.readouterr()

    assert result == 1
    assert "Status: failed" in captured.out
    assert "RuntimeError: Execution failed." in captured.out


def test_workflow_run_persists_successful_run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_runtime(
        monkeypatch,
        tmp_path,
        create_runtime(),
    )

    result = run_workflow(WORKFLOW_ID)

    captured = capsys.readouterr()

    runs = SQLiteWorkflowRunRepository(database).runs_for_workflow(WORKFLOW_ID)

    assert result == 0
    assert len(runs) == 1
    assert runs[0].succeeded
    assert f"Run ID: {runs[0].id}\n" in captured.out


def test_workflow_run_persists_failed_run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    failed = create_failed_run()

    database = configure_failed_execution(
        monkeypatch,
        tmp_path,
        failed,
    )

    result = run_workflow(WORKFLOW_ID)

    assert result == 1
    assert SQLiteWorkflowRunRepository(database).get(failed.id) == failed


def test_workflow_run_does_not_persist_when_candidate_cannot_be_generated(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    database = configure_runtime(
        monkeypatch,
        tmp_path,
        create_runtime(),
    )

    result = run_workflow(UNKNOWN_WORKFLOW_ID)

    assert result == 1
    assert SQLiteWorkflowRunRepository(database).runs() == ()
