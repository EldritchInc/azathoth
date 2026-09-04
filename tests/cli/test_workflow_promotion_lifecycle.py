"""End-to-end tests for workflow promotion through the CLI."""

from pathlib import Path
from uuid import UUID

import pytest

import azathoth.cli.bootstrap as cli_bootstrap
from azathoth.cli import (
    DATABASE_ENVIRONMENT_VARIABLE,
    main,
)
from azathoth.prompting import (
    FixedModelSelection,
    PromptStrategySpec,
)
from azathoth.providers import (
    DeterministicLanguageModel,
    LanguageModelRegistry,
    ModelCatalog,
    ModelMetadata,
    Prompt,
)
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    SQLiteProductionInvocationRepository,
    SQLiteProductionInvocationRunRepository,
    SQLiteWorkflowProductionRevisionRepository,
    SQLiteWorkflowProductionStateRepository,
    SQLiteWorkflowRepository,
    SQLiteWorkflowRunRepository,
    WorkflowMetadata,
    WorkflowSpecification,
    WorkflowStepSpecification,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")
STEP_ID = UUID("22222222-2222-2222-2222-222222222222")
STRATEGY_ID = UUID("33333333-3333-3333-3333-333333333333")

MODEL = FixedModelSelection(
    provider="test-provider",
    model="production-model",
)


def create_workflow() -> WorkflowSpecification:
    """Create one deterministic configured workflow."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="promotion-cli-lifecycle",
            description="Exercise promotion through the installed CLI.",
            version="1.0.0",
        ),
        steps=(
            WorkflowStepSpecification(
                id=STEP_ID,
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=STRATEGY_ID,
                        name="production-prompt",
                        description="Return deterministic production output.",
                        version="1.0.0",
                    ),
                    prompt=Prompt(
                        text="Return the deterministic production response.",
                    ),
                    model_selection=MODEL,
                ),
            ),
        ),
    )


def create_catalog() -> ModelCatalog:
    """Create deterministic current provider model metadata."""

    return ModelCatalog(
        models=(
            ModelMetadata(
                provider=MODEL.provider,
                model=MODEL.model,
                display_name=MODEL.identifier,
            ),
        )
    )


def create_registry() -> LanguageModelRegistry:
    """Create deterministic executable language models."""

    return LanguageModelRegistry(
        {
            MODEL.identifier: DeterministicLanguageModel(
                provider=MODEL.provider,
                model=MODEL.model,
                response_text="production-success",
            ),
        }
    )


def configure_cli_runtime(
    *,
    database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Configure deterministic provider truth for real CLI runtime loading."""

    monkeypatch.setenv(
        DATABASE_ENVIRONMENT_VARIABLE,
        str(database),
    )

    monkeypatch.setattr(
        cli_bootstrap,
        "_load_current_models",
        lambda _configuration: create_catalog(),
    )

    monkeypatch.setattr(
        cli_bootstrap,
        "_load_language_models",
        lambda *, configuration, models: create_registry(),
    )


def test_cli_promotion_persists_active_state_and_revision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    configured = create_workflow()

    SQLiteWorkflowRepository(
        database,
    ).save(
        configured,
    )

    configure_cli_runtime(
        database=database,
        monkeypatch=monkeypatch,
    )

    result = main(
        (
            "workflow",
            "promote",
            str(WORKFLOW_ID),
        )
    )

    captured = capsys.readouterr()

    assert result == 0
    assert captured.err == ""

    state = SQLiteWorkflowProductionStateRepository(
        database,
    ).get(
        WORKFLOW_ID,
    )

    assert state is not None
    assert state.specification.metadata == configured.metadata
    assert len(state.specification.steps) == 1

    production_step = state.specification.steps[0]

    assert production_step.id == STEP_ID
    assert isinstance(
        production_step.specification,
        PromptStrategySpec,
    )

    assert production_step.specification.model_selection == MODEL

    revisions = SQLiteWorkflowProductionRevisionRepository(
        database,
    ).revisions_for_workflow(
        WORKFLOW_ID,
    )

    assert len(revisions) == 1

    revision = revisions[0]

    assert revision.state == state

    assert f"Workflow ID: {WORKFLOW_ID}\n" in captured.out
    assert f"Revision ID: {revision.id}\n" in captured.out
    assert "Status: promoted\n" in captured.out
    assert f"Prompt Step: {STEP_ID}\n" in captured.out
    assert f"Primary Model: {MODEL.identifier}" in captured.out


def test_cli_promoted_workflow_is_immediately_invokable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    SQLiteWorkflowRepository(
        database,
    ).save(
        create_workflow(),
    )

    configure_cli_runtime(
        database=database,
        monkeypatch=monkeypatch,
    )

    assert (
        main(
            (
                "workflow",
                "promote",
                str(WORKFLOW_ID),
            )
        )
        == 0
    )

    capsys.readouterr()

    result = main(
        (
            "workflow",
            "invoke",
            str(WORKFLOW_ID),
            "--input",
            '{"request":"execute production"}',
        )
    )

    captured = capsys.readouterr()

    assert result == 0
    assert captured.err == ""

    state = SQLiteWorkflowProductionStateRepository(
        database,
    ).get(
        WORKFLOW_ID,
    )

    assert state is not None

    revisions = SQLiteWorkflowProductionRevisionRepository(
        database,
    ).revisions_for_workflow(
        WORKFLOW_ID,
    )

    assert len(revisions) == 1
    assert revisions[0].state == state

    invocation_repository = SQLiteProductionInvocationRepository(
        database,
    )

    invocation_run_repository = SQLiteProductionInvocationRunRepository(
        database,
    )

    run_repository = SQLiteWorkflowRunRepository(
        database,
    )

    invocations = invocation_repository.invocations()

    assert len(invocations) == 1
    assert invocations[0].workflow_id == WORKFLOW_ID

    association = invocation_run_repository.get(
        invocations[0].id,
    )

    assert association is not None

    run = run_repository.get(
        association.run_id,
    )

    assert run is not None
    assert run.workflow.id == WORKFLOW_ID

    assert run.steps[0].execution is not None
    assert run.steps[0].execution.output == "production-success"

    assert "Status: succeeded\n" in captured.out
