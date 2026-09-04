"""End-to-end tests for production workflow invocation through the CLI."""

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
    ProductionInvocationErrorCode,
    ProductionInvocationFailure,
    ProductionInvocationSuccess,
    SQLiteProductionInvocationRepository,
    SQLiteProductionInvocationRunRepository,
    SQLiteWorkflowProductionStateRepository,
    SQLiteWorkflowRunRepository,
    WorkflowMetadata,
    WorkflowProductionEmission,
    WorkflowProductionState,
    WorkflowSpecification,
    WorkflowStepSpecification,
    WorkflowValueBinding,
    WorkflowValueReference,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

UNDEPLOYED_WORKFLOW_ID = UUID("22222222-2222-2222-2222-222222222222")

STEP_ID = UUID("33333333-3333-3333-3333-333333333333")

STRATEGY_ID = UUID("44444444-4444-4444-4444-444444444444")

MODEL = FixedModelSelection(
    provider="test-provider",
    model="production-model",
)


def create_state() -> WorkflowProductionState:
    """Create one deterministic active production workflow."""

    return WorkflowProductionState(
        specification=WorkflowSpecification(
            metadata=WorkflowMetadata(
                id=WORKFLOW_ID,
                name="production-cli-lifecycle",
                description="Exercise production invocation through the CLI.",
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
                    outputs=(
                        WorkflowValueBinding(
                            name="answer",
                        ),
                    ),
                ),
            ),
        ),
        emissions=(
            WorkflowProductionEmission(
                name="public_answer",
                source=WorkflowValueReference(
                    producer_step_id=STEP_ID,
                    name="answer",
                ),
            ),
        ),
    )


def create_catalog() -> ModelCatalog:
    """Create deterministic current production model metadata."""

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
    """Create deterministic executable production models."""

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


def test_cli_production_invocation_persists_complete_lifecycle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    state = create_state()

    SQLiteWorkflowProductionStateRepository(
        database,
    ).set(
        state,
    )

    configure_cli_runtime(
        database=database,
        monkeypatch=monkeypatch,
    )

    result = main(
        (
            "workflow",
            "invoke",
            str(WORKFLOW_ID),
            "--input",
            '{"request":"execute production","private":"do not expose"}',
        )
    )

    captured = capsys.readouterr()

    assert result == 0
    assert captured.err == ""

    invocation_repository = SQLiteProductionInvocationRepository(
        database,
    )

    run_repository = SQLiteWorkflowRunRepository(
        database,
    )

    invocation_run_repository = SQLiteProductionInvocationRunRepository(
        database,
    )

    invocations = invocation_repository.invocations()

    assert len(invocations) == 1

    invocation = invocations[0]

    assert invocation.workflow_id == WORKFLOW_ID

    terminal_result = invocation_repository.result(
        invocation.id,
    )

    assert isinstance(
        terminal_result,
        ProductionInvocationSuccess,
    )

    assert terminal_result.result == {
        "public_answer": "production-success",
    }

    association = invocation_run_repository.get(
        invocation.id,
    )

    assert association is not None

    run = run_repository.get(
        association.run_id,
    )

    assert run is not None
    assert run.workflow.id == WORKFLOW_ID
    assert run.initial_context == invocation.initial_context

    assert run.steps[0].execution is not None
    assert run.steps[0].execution.output == "production-success"

    assert f"Invocation ID: {invocation.id}\n" in captured.out
    assert "Status: succeeded\n" in captured.out
    assert "Result:\n" in captured.out
    assert '"public_answer": "production-success"' in captured.out

    assert "private" not in captured.out
    assert "Workflow ID:" not in captured.out
    assert "Run ID:" not in captured.out
    assert "Step " not in captured.out
    assert "Strategy:" not in captured.out
    assert "Provider:" not in captured.out
    assert "Model:" not in captured.out
    assert "Attempts:" not in captured.out


def test_cli_undeployed_production_invocation_persists_terminal_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    configure_cli_runtime(
        database=database,
        monkeypatch=monkeypatch,
    )

    result = main(
        (
            "workflow",
            "invoke",
            str(UNDEPLOYED_WORKFLOW_ID),
            "--input",
            '{"request":"execute production"}',
        )
    )

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""

    invocation_repository = SQLiteProductionInvocationRepository(
        database,
    )

    run_repository = SQLiteWorkflowRunRepository(
        database,
    )

    invocation_run_repository = SQLiteProductionInvocationRunRepository(
        database,
    )

    invocations = invocation_repository.invocations()

    assert len(invocations) == 1

    invocation = invocations[0]

    assert invocation.workflow_id == UNDEPLOYED_WORKFLOW_ID

    terminal_result = invocation_repository.result(
        invocation.id,
    )

    assert isinstance(
        terminal_result,
        ProductionInvocationFailure,
    )

    assert terminal_result.error_code is ProductionInvocationErrorCode.WORKFLOW_NOT_DEPLOYED

    assert f"Invocation ID: {invocation.id}\n" in captured.err
    assert "Status: failed\n" in captured.err
    assert f"Error: {ProductionInvocationErrorCode.WORKFLOW_NOT_DEPLOYED.value}\n" in captured.err

    assert run_repository.runs() == ()
    assert invocation_run_repository.associations() == ()


def test_cli_production_invocation_uses_persisted_active_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    state = create_state()

    state_repository = SQLiteWorkflowProductionStateRepository(
        database,
    )

    state_repository.set(
        state,
    )

    configure_cli_runtime(
        database=database,
        monkeypatch=monkeypatch,
    )

    assert (
        main(
            (
                "workflow",
                "invoke",
                str(WORKFLOW_ID),
                "--input",
                '"production request"',
            )
        )
        == 0
    )

    captured = capsys.readouterr()

    assert '"public_answer": "production-success"' in captured.out

    reconstructed_state = SQLiteWorkflowProductionStateRepository(
        database,
    ).get(
        WORKFLOW_ID,
    )

    assert reconstructed_state == state
